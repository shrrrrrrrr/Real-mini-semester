"""SQLAlchemy ORM 模型：本地 SQLite 的 11 张核心表。

单用户本地应用，故所有表不再携带 user_id（相对云架构砍掉了账号体系）。
设计要点：
- chunks.locator_value 记录格式相关的定位符（页码/幻灯片号/章节/行号），
  是引用溯源的关键字段；
- messages.segments 存双层答案（doc/general 分区）；
- flashcards 内嵌 FSRS 调度状态，due 建索引支撑到期查询；
- messages.parent_message_id 预留树形字段（V1.5 多分支提问启用）。
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 课程与资料
# ---------------------------------------------------------------------------


class Course(Base):
    """课程：资料、问答、测验、闪卡都以课程为组织单位。"""

    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(primary_key=True)  # UUID
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    # 级联声明：删课程时连带清理测验/闪卡/计划（外键有 ON DELETE 行为的
    # review_logs 由数据库层兜底，其余走 ORM 级联）
    quizzes: Mapped[list["Quiz"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    flashcards: Mapped[list["Flashcard"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    review_plans: Mapped[list["ReviewPlan"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    explains: Mapped[list["Explain"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Document(Base):
    """资料文档：上传原件存本地目录，本表存元数据与解析状态。

    status 状态机：pending → parsing → indexed / failed / rejected
    - rejected 专用于扫描版 PDF 等无法提取文本的情况（明示拒收原因）。
    """

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(primary_key=True)  # UUID
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)  # pdf/docx/pptx/epub/txt/md
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)  # 原件本地路径
    # 定位符类型：page（PDF）/ paragraph（DOCX）/ slide（PPTX）/ section（EPUB）/ line（TXT/MD）
    locator_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    fail_reason: Mapped[str | None] = mapped_column(Text, default=None)
    include_in_rag: Mapped[bool] = mapped_column(Boolean, default=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    course: Mapped["Course"] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """文本块：检索的最小单位，携带原文与 384 维向量（JSONB 存 JSON 字符串）。

    向量存 SQLite JSON 列而非引入向量数据库：课程级规模（数千块）下
    内存余弦计算 < 50ms，自实现检索完全可解释（规模边界见开发文档 §8.2）。
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_document_idx", "document_id", "chunk_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # 定位符值：页码/幻灯片号/章节名/行号——引用展示用（如"第 12 页"）
    locator_value: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, default=None)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped["Document"] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# 问答（双层答案）
# ---------------------------------------------------------------------------


class ChatSession(Base):
    """一次问答会话（按课程组织）。"""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(Text, default="新对话")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    course: Mapped["Course"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    """消息：segments 存双层答案分区，citations 存引用片段（由后端从 chunks 原样取出）。

    parent_message_id 预留树形结构（V1.5 多分支提问），V1 恒为 NULL。
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    parent_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), default=None
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 双层答案分区：[{"layer": "doc"|"general", "text": "..."}]
    segments: Mapped[list | None] = mapped_column(JSON, default=None)
    # 引用列表：[{"index": 1, "chunk_id": 5, "filename": "...", "locator": "第12页", "snippet": "..."}]
    citations: Mapped[list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


# ---------------------------------------------------------------------------
# 讲解模式
# ---------------------------------------------------------------------------


class Explain(Base):
    """讲解大纲：按书名/学科/章节生成的结构化大纲，节点可挂接已上传资料片段。"""

    __tablename__ = "explains"

    id: Mapped[str] = mapped_column(primary_key=True)  # UUID
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    # 大纲树：[{"title": "...", "nodes": [{"title": "...", "linked_chunk_ids": []}]}]
    outline: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    course: Mapped["Course | None"] = relationship(back_populates="explains")


# ---------------------------------------------------------------------------
# 测验
# ---------------------------------------------------------------------------


class Quiz(Base):
    """一次测验。"""

    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    course: Mapped["Course"] = relationship(back_populates="quizzes")
    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan"
    )


class QuizQuestion(Base):
    """测验题目：仅从资料内容生成；answer 字段仅在判分后返回给前端。"""

    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"), index=True)
    question_no: Mapped[int] = mapped_column(Integer, nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSON, nullable=False)  # 恰好 4 项
    answer: Mapped[str] = mapped_column(Text, nullable=False)  # "A"-"D"
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    difficulty: Mapped[str] = mapped_column(Text, nullable=False, default="基础")
    source_chunk_ids: Mapped[list | None] = mapped_column(JSON, default=None)

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")
    attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class QuizAttempt(Base):
    """答题记录：每次作答一条，支撑正确率统计与错题定位。"""

    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("quiz_questions.id"), index=True
    )
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"), index=True)
    selected: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(default=utcnow)

    question: Mapped["QuizQuestion"] = relationship(back_populates="attempts")


# ---------------------------------------------------------------------------
# 闪卡与复习
# ---------------------------------------------------------------------------


class Flashcard(Base):
    """闪卡：内嵌 FSRS 调度状态（stability/difficulty/state/reps/lapses）。

    origin 标记来源：quiz（错题转卡）或 manual（手动创建）；
    origin_question_id 回链错题，支撑冲刺模式的"错题卡优先"排序。
    """

    __tablename__ = "flashcards"
    __table_args__ = (
        UniqueConstraint("course_id", "origin_question_id"),
        Index("ix_flashcards_due", "due"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    origin_question_id: Mapped[str | None] = mapped_column(
        ForeignKey("quiz_questions.id"), default=None
    )
    # ---- FSRS 调度状态（由前端 ts-fsrs 计算，后端持久化）----
    due: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    stability: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[int] = mapped_column(Integer, default=0)  # 0new 1learning 2review 3relearning
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    last_review: Mapped[datetime | None] = mapped_column(default=None)

    course: Mapped["Course"] = relationship(back_populates="flashcards")
    logs: Mapped[list["ReviewLog"]] = relationship(
        back_populates="flashcard", cascade="all, delete-orphan"
    )


class ReviewLog(Base):
    """复习日志：每次评分的原始记录，统计分析与后续 FSRS 个人化优化的数据基础。"""

    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flashcard_id: Mapped[str] = mapped_column(
        ForeignKey("flashcards.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4
    review_time: Mapped[datetime] = mapped_column(default=utcnow)
    scheduled_days: Mapped[float] = mapped_column(Float, default=0.0)
    elapsed_days: Mapped[float] = mapped_column(Float, default=0.0)

    flashcard: Mapped["Flashcard"] = relationship(back_populates="logs")


class ReviewPlan(Base):
    """复习计划：冲刺模式（考试日期+预算）或手动模式（范围+每日卡量）。

    status 优先级：manual > sprint > 长期（FSRS 默认），同一课程同时只有一个 active。
    """

    __tablename__ = "review_plans"

    id: Mapped[str] = mapped_column(primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)  # sprint / manual
    exam_date: Mapped[date | None] = mapped_column(Date, default=None)
    daily_budget_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    daily_card_count: Mapped[int | None] = mapped_column(Integer, default=None)
    # 范围：{"only_wrong": bool}（V1 简化为"是否仅错题卡"）
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    # 逐日计划：[{"date": "2026-09-10", "card_ids": [...], "est_minutes": 20}]
    plan_days: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(Text, default="active")  # active/finished/archived
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    course: Mapped["Course"] = relationship(back_populates="review_plans")
