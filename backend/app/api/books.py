"""书库接口：全局共享电子图书（上传/删除/列表）+ 像素风占位封面生成。

复用 Document 的解析索引管线（chunks 通用，owner=book）。
问答/测验勾选书库范围：检索时把选中书的 chunks 与课程资料合并。
"""

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.indexer import file_type_of, save_upload
from app.core.parser import LOCATOR_TYPES
from app.db import get_db
from app.models import Book, Chunk

router = APIRouter()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 大部头教材上限 200MB

# 书库封面只使用北航蓝与薄荷绿；每本书的像素排布由标题哈希稳定生成。
COVER_BLUE = "#247fb8"
COVER_GREEN = "#75bfa6"


def make_cover(title: str) -> str:
    """按书名生成蓝绿像素风占位封面（标题哈希 + 16×16 像素块图案）。

    输出 data URL（PNG base64）——小图直接内联存储，无需静态目录。
    图案：伪随机（标题哈希种子）的对称像素图案，每本书稳定不变。
    """
    seed = abs(hash(title)) % (2**32)
    fg, bg = (COVER_BLUE, COVER_GREEN) if seed % 2 else (COVER_GREEN, COVER_BLUE)

    def rgb(hexc: str):
        return tuple(int(hexc[i : i + 2], 16) for i in (1, 3, 5))

    fg_rgb, bg_rgb = rgb(fg), rgb(bg)
    img = Image.new("RGB", (16, 16), bg_rgb)
    # 伪随机对称图案（左上 8×8 镜像到四象限，像素艺术惯例）
    cells = {}
    x = seed
    for yy in range(8):
        for xx in range(8):
            x = (x * 1103515245 + 12345) % (2**31)
            on = (x // 65536) % 3 == 0
            cells[(xx, yy)] = on
    for (xx, yy), on in cells.items():
        if on:
            for mx, my in ((xx, yy), (15 - xx, yy), (xx, 15 - yy), (15 - xx, 15 - yy)):
                img.putpixel((mx, my), fg_rgb)
    # 标题首字放大叠加（中英文均可读）
    img = img.resize((320, 320), Image.NEAREST)
    draw = ImageDraw.Draw(img)
    ch = title.strip()[0] if title.strip() else "书"
    # 用系统默认字体画大字（PIL 无中文字体时的兜底：色块代替字符）
    try:
        draw.text((160, 160), ch, fill=bg_rgb, anchor="mm")
    except Exception:
        pass

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    import base64

    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class BookUpdate(BaseModel):
    """只允许编辑展示书名；原文件与索引不受影响。"""

    title: str = Field(min_length=1, max_length=120)


class BookOut(BaseModel):
    id: str
    title: str
    cover: str | None
    filename: str
    file_type: str
    status: str
    fail_reason: str | None
    page_count: int
    chunk_count: int
    created_at: str

    class Config:
        from_attributes = True


def _to_out(b: Book) -> BookOut:
    return BookOut(
        id=b.id,
        title=b.title,
        cover=b.cover,
        filename=b.filename,
        file_type=b.file_type,
        status=b.status,
        fail_reason=b.fail_reason,
        page_count=b.page_count,
        chunk_count=b.chunk_count,
        created_at=b.created_at.isoformat(),
    )


@router.get("/books", response_model=list[BookOut])
def list_books(db: Session = Depends(get_db)):
    """书库列表（全局共享）。"""
    books = db.scalars(select(Book).order_by(Book.created_at.desc())).all()
    return [_to_out(b) for b in books]


@router.post("/books", response_model=BookOut, status_code=201)
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db),
):
    """上传图书：秒回（pending），后台解析索引（大书耗时几分钟也不阻塞）。

    title 空时取文件名去扩展名；封面自动生成像素风占位图。
    """
    ftype = file_type_of(file.filename or "")
    if ftype is None:
        raise HTTPException(400, "不支持的格式：仅支持 pdf/epub/txt/md")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "文件过大（上限 200MB）")
    if not content:
        raise HTTPException(400, "空文件")

    book_title = (title or "").strip() or (file.filename or "未命名").rsplit(".", 1)[0]
    from app.config import settings as _settings

    stored = save_upload(_settings.upload_dir / "books", file.filename or "book", content)
    book = Book(
        id=uuid.uuid4().hex,
        title=book_title,
        cover=make_cover(book_title),
        filename=file.filename or "book",
        file_type=ftype,
        stored_path=str(stored),
        locator_type=LOCATOR_TYPES[ftype],
        status="pending",
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    spawn_book_index_task(book.id).start()
    return _to_out(book)


@router.patch("/books/{book_id}", response_model=BookOut)
def update_book(book_id: str, body: BookUpdate, db: Session = Depends(get_db)):
    """重命名书库条目，并按新标题生成新的蓝绿像素封面。"""
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "图书不存在")
    book.title = body.title.strip()
    book.cover = make_cover(book.title)
    db.commit()
    db.refresh(book)
    return _to_out(book)


@router.delete("/books/{book_id}", status_code=204)
def delete_book(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "图书不存在")
    # 手动清块（chunks.owner=book 无 FK 级联）
    db.query(Chunk).filter(Chunk.owner == "book", Chunk.document_id == book_id).delete()
    db.delete(book)
    db.commit()
    try:
        Path(book.stored_path).unlink(missing_ok=True)
    except OSError:
        pass


@router.post("/books/{book_id}/reindex", response_model=BookOut)
def reindex_book(book_id: str, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "图书不存在")
    book.status = "pending"
    book.fail_reason = None
    db.commit()
    spawn_book_index_task(book_id).start()
    db.refresh(book)
    return _to_out(book)


# ---------------------------------------------------------------------------
# 索引（复用 Document 管线，仅 owner 与挂载表不同）
# ---------------------------------------------------------------------------


def index_book_sync(db: Session, book_id: str) -> None:
    """同步索引一本图书：解析 → 分块 → 嵌入 → chunks（owner=book）。"""
    from pathlib import Path

    from app.core.chunker import chunk_units
    from app.core.parser import ScannedPdfError, parse_file
    from app.core.retrieval import embed_texts

    book = db.get(Book, book_id)
    if book is None:
        return
    book.status = "parsing"
    db.commit()
    try:
        units = parse_file(Path(book.stored_path), book.file_type)
        if not units:
            raise ValueError("解析结果为空：文件中未提取到任何文本")
        raw_chunks = chunk_units(units)
        if not raw_chunks:
            raise ValueError("分块结果为空：内容过短或格式异常")
        embeddings = embed_texts([c["content"] for c in raw_chunks])

        db.query(Chunk).filter(
            Chunk.owner == "book", Chunk.document_id == book_id
        ).delete()
        for i, c in enumerate(raw_chunks):
            db.add(
                Chunk(
                    owner="book",
                    document_id=book_id,  # 存 books.id
                    chunk_index=i,
                    locator_value=c["locator"],
                    content=c["content"],
                    embedding=embeddings[i],
                    token_count=c["token_count"],
                )
            )
        book.page_count = len(units)
        book.chunk_count = len(raw_chunks)
        book.status = "indexed"
        book.fail_reason = None
        db.commit()
    except ScannedPdfError as e:
        book.status = "rejected"
        book.fail_reason = str(e)
        db.commit()
    except Exception as e:
        book.status = "failed"
        book.fail_reason = f"解析失败：{e}"
        db.commit()


def spawn_book_index_task(book_id: str):
    """后台线程包装（独立 DB 会话）。"""
    import threading

    from app.db import SessionLocal

    def _run():
        db = SessionLocal()
        try:
            index_book_sync(db, book_id)
        finally:
            db.close()

    return threading.Thread(target=_run, daemon=True, name=f"bookidx-{book_id[:8]}")


def load_book_chunks(db: Session, book_ids: list[str]) -> list:
    """取选中书库的已索引 chunks（供检索合并）。"""
    if not book_ids:
        return []
    return db.scalars(
        select(Chunk)
        .join(Book, Chunk.document_id == Book.id)
        .where(
            Chunk.owner == "book",
            Book.status == "indexed",
            Chunk.document_id.in_(book_ids),
        )
        .order_by(Chunk.document_id, Chunk.chunk_index)
    ).all()
