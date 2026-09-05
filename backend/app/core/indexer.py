"""索引器：解析 → 分块 → 嵌入 → 入库的异步后台任务。

状态机（开发文档 §5.3 难点 4）：
pending → parsing → indexed / failed / rejected
上传接口立即返回，索引在后台线程执行，前端轮询状态徽章展示进度。
"""

import threading
import traceback
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.chunker import chunk_units
from app.core.llm import LLMError
from app.core.parser import LOCATOR_TYPES, ScannedPdfError, parse_file
from app.core.retrieval import embed_texts
from app.models import Chunk, Document


def save_upload(course_dir: Path, filename: str, content: bytes) -> Path:
    """保存上传原件：文件名加 UUID 前缀避免重名覆盖。"""
    course_dir.mkdir(parents=True, exist_ok=True)
    safe = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
    path = course_dir / safe
    path.write_bytes(content)
    return path


def file_type_of(filename: str) -> str | None:
    """从文件名扩展名推断受支持的格式；不支持返回 None。"""
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext if ext in LOCATOR_TYPES else None


def index_document_sync(db: Session, document_id: str) -> None:
    """同步索引一个文档（在后台线程中运行）。

    任何异常都转为 failed/rejected 状态落库，不抛出——
    保证后台线程不会因单个文档失败而崩溃。
    """
    doc = db.get(Document, document_id)
    if doc is None:
        return
    doc.status = "parsing"
    db.commit()
    # 结束当前事务释放潜在锁；session 保持可用（后续状态更新复用）
    try:
        units = parse_file(Path(doc.stored_path), doc.file_type)
        if not units:
            raise ValueError("解析结果为空：文件中未提取到任何文本")
        raw_chunks = chunk_units(units)
        if not raw_chunks:
            raise ValueError("分块结果为空：内容过短或格式异常")

        # 批量嵌入（MiniLM 本地计算，无需 API）
        embeddings = embed_texts([c["content"] for c in raw_chunks])

        # 落库：先清旧块（支持重新索引）
        db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
        for i, c in enumerate(raw_chunks):
            db.add(
                Chunk(
                    document_id=doc.id,
                    chunk_index=i,
                    locator_value=c["locator"],
                    content=c["content"],
                    embedding=embeddings[i],
                    token_count=c["token_count"],
                )
            )
        doc.page_count = len(units)
        doc.chunk_count = len(raw_chunks)
        doc.locator_type = LOCATOR_TYPES[doc.file_type]
        doc.status = "indexed"
        doc.fail_reason = None
        db.commit()
    except ScannedPdfError as e:
        # 扫描件：明示拒收（开发文档 §5.2 技术点④的边界处理）
        doc.status = "rejected"
        doc.fail_reason = str(e)
        db.commit()
    except (LLMError, ValueError) as e:
        doc.status = "failed"
        doc.fail_reason = f"解析失败：{e}"
        db.commit()
    except Exception as e:  # 兜底：未知异常也落状态而不是让线程崩溃
        doc.status = "failed"
        doc.fail_reason = f"解析异常：{e}"
        db.commit()
        traceback.print_exc()


def reindex_all_sync(db: Session, document_id: str) -> None:
    """重新索引入口（与首次索引共用逻辑，别名保留给 API 层语义）。"""
    index_document_sync(db, document_id)


def spawn_index_task(document_id: str) -> threading.Thread:
    """创建后台索引线程（由上传接口调用后立即 start）。

    线程内独立开 DB 会话，避免与请求会话交叉。
    """
    from app.db import SessionLocal

    def _run():
        db = SessionLocal()
        try:
            index_document_sync(db, document_id)
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True, name=f"index-{document_id[:8]}")
    return t
