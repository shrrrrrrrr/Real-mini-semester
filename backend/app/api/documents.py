"""课程与资料管理接口：建课程 / 上传（后台索引）/ 勾选范围 / 删除。"""

import asyncio
import datetime as dt
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_schemas import CourseCreate, CourseOut, DocumentOut, DocumentPatch
from app.config import settings
from app.core.indexer import file_type_of, save_upload, spawn_index_task
from app.core.parser import LOCATOR_TYPES
from app.db import get_db
from app.models import Chunk, Course, Document, Flashcard

router = APIRouter()

# 上传大小上限（60MB：电子教材可能较大）
MAX_UPLOAD_BYTES = 60 * 1024 * 1024


def get_course_or_404(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课程不存在")
    return course


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db)):
    """课程列表（含资料数/就绪数/闪卡数/到期数聚合，供资料库侧栏展示）。"""
    courses = db.scalars(select(Course).order_by(Course.created_at.desc())).all()
    out = []
    now = dt.datetime.now(dt.timezone.utc)
    for c in courses:
        doc_count = db.scalar(
            select(func.count()).where(Document.course_id == c.id)
        )
        indexed = db.scalar(
            select(func.count()).where(
                Document.course_id == c.id, Document.status == "indexed"
            )
        )
        card_count = db.scalar(
            select(func.count()).where(Flashcard.course_id == c.id)
        )
        due = db.scalar(
            select(func.count()).where(Flashcard.course_id == c.id, Flashcard.due <= now)
        )
        out.append(
            CourseOut(
                id=c.id,
                name=c.name,
                created_at=c.created_at,
                document_count=doc_count or 0,
                indexed_count=indexed or 0,
                flashcard_count=card_count or 0,
                due_count=due or 0,
            )
        )
    return out


@router.post("/courses", response_model=CourseOut)
def create_course(body: CourseCreate, db: Session = Depends(get_db)):
    course = Course(id=uuid.uuid4().hex, name=body.name.strip())
    db.add(course)
    db.commit()
    db.refresh(course)
    return CourseOut(
        id=course.id,
        name=course.name,
        created_at=course.created_at,
    )


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: str, db: Session = Depends(get_db)):
    course = get_course_or_404(db, course_id)
    db.delete(course)  # 级联删除资料/块/会话
    db.commit()


@router.get("/courses/{course_id}/documents", response_model=list[DocumentOut])
def list_documents(course_id: str, db: Session = Depends(get_db)):
    get_course_or_404(db, course_id)
    docs = db.scalars(
        select(Document)
        .where(Document.course_id == course_id)
        .order_by(Document.created_at.desc())
    ).all()
    return docs


@router.post(
    "/courses/{course_id}/documents", response_model=DocumentOut, status_code=201
)
async def upload_document(
    course_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传原件：秒回（status=pending），后台线程异步解析索引。

    格式校验在上传时即完成（扩展名白名单），扫描件检测在索引阶段
    （parse 阶段抛 ScannedPdfError → status=rejected）。
    """
    get_course_or_404(db, course_id)
    ftype = file_type_of(file.filename or "")
    if ftype is None:
        raise HTTPException(400, "不支持的格式：仅支持 pdf/docx/pptx/epub/txt/md")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "文件过大（上限 60MB）")
    if not content:
        raise HTTPException(400, "空文件")

    # 原件落盘 + 元数据入库
    stored = save_upload(settings.upload_dir / course_id, file.filename or "unnamed", content)
    doc = Document(
        id=uuid.uuid4().hex,
        course_id=course_id,
        filename=file.filename or "unnamed",
        file_type=ftype,
        stored_path=str(stored),
        locator_type=LOCATOR_TYPES[ftype],
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 后台索引（线程执行，避免阻塞事件循环；DB 会话在线程内独立创建）
    task = spawn_index_task(doc.id)
    task.start()
    # 让出事件循环，确保 pending 状态先落库可见
    await asyncio.sleep(0)

    return doc


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
def patch_document(doc_id: str, body: DocumentPatch, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "资料不存在")
    if body.include_in_rag is not None:
        doc.include_in_rag = body.include_in_rag
        db.commit()
        db.refresh(doc)
    return doc


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "资料不存在")
    db.delete(doc)  # 级联删块；原件一并清理
    db.commit()
    try:
        Path(doc.stored_path).unlink(missing_ok=True)
    except OSError:
        pass  # 原件清理失败不影响元数据一致性


@router.post("/documents/{doc_id}/reindex", response_model=DocumentOut)
def reindex_document(doc_id: str, db: Session = Depends(get_db)):
    """重新索引（解析失败的文件修复后重试）。"""
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "资料不存在")
    doc.status = "pending"
    doc.fail_reason = None
    db.commit()
    spawn_index_task(doc.id).start()
    db.refresh(doc)
    return doc


# 供其他模块复用的检索过滤查询（勾选范围 + 已就绪）
def select_indexed_chunks(db: Session, course_id: str):
    return db.scalars(
        select(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.course_id == course_id,
            Document.include_in_rag.is_(True),
            Document.status == "indexed",
        )
        .order_by(Chunk.document_id, Chunk.chunk_index)
    ).all()
