"""数据库会话管理：本地 SQLite + SQLAlchemy。

使用 check_same_thread=False（FastAPI 多线程访问 SQLite 连接），
WAL 模式提升并发读写表现。
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# 建库目录（data/ 若不存在则创建）
settings.db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _):
    """开启 WAL：读写不互斥，前端轮询解析状态时不会阻塞写入。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个会话，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表：幂等（表已存在则跳过）。"""
    from app import models  # noqa: F401  确保模型注册

    Base = models.Base
    Base.metadata.create_all(engine)
