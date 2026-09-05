"""API 请求/响应模型（Pydantic）：前后端契约。

注意与 app/core/prompts.py 中 LLM 输出契约的分工：
- 本文件约束 HTTP 接口（前端 ↔ 后端）；
- prompts.py 约束 LLM 输出（模型 ↔ 后端）。
"""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 课程与资料
# ---------------------------------------------------------------------------


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CourseOut(BaseModel):
    id: str
    name: str
    created_at: dt.datetime
    document_count: int = 0
    indexed_count: int = 0
    flashcard_count: int = 0
    due_count: int = 0

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    locator_type: str
    status: str
    fail_reason: str | None
    include_in_rag: bool
    page_count: int
    chunk_count: int
    created_at: dt.datetime

    class Config:
        from_attributes = True


class DocumentPatch(BaseModel):
    include_in_rag: bool | None = None


# ---------------------------------------------------------------------------
# 问答
# ---------------------------------------------------------------------------


class ChatAsk(BaseModel):
    """提问请求：可指定会话（多轮），不传则新建会话。"""

    course_id: str
    session_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)


class CitationOut(BaseModel):
    index: int
    chunk_id: int
    filename: str
    locator: str
    snippet: str


class SegmentOut(BaseModel):
    layer: Literal["doc", "general"]
    text: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    segments: list[SegmentOut] | None
    citations: list[CitationOut] | None
    created_at: dt.datetime

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# 讲解
# ---------------------------------------------------------------------------


class ExplainCreate(BaseModel):
    course_id: str | None = None
    topic: str = Field(min_length=1, max_length=200)


class ExplainNodeOut(BaseModel):
    title: str
    summary: str
    linked_hint: str
    linked_chunk_ids: list[int] = Field(default_factory=list)


class ExplainSectionOut(BaseModel):
    title: str
    nodes: list[ExplainNodeOut]


class ExplainOut(BaseModel):
    id: str
    course_id: str | None
    topic: str
    sections: list[ExplainSectionOut]
    created_at: dt.datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# 测验
# ---------------------------------------------------------------------------


class QuizCreate(BaseModel):
    course_id: str
    count: int = Field(default=5, ge=1, le=10)


class QuizQuestionOut(BaseModel):
    """判分前 answer 不返回（防止答案泄露到前端）。"""

    id: int
    question_no: int
    stem: str
    options: list[str]
    difficulty: str


class QuizOut(BaseModel):
    id: str
    course_id: str
    question_count: int
    created_at: dt.datetime
    questions: list[QuizQuestionOut]


class QuizAnswerIn(BaseModel):
    question_id: int
    selected: Literal["A", "B", "C", "D"]


class QuizSubmit(BaseModel):
    answers: list[QuizAnswerIn]


class QuizResultItem(BaseModel):
    question_id: int
    selected: str
    answer: str  # 判分后才返回正确答案
    is_correct: bool
    explanation: str
    stem: str
    options: list[str]


class QuizSubmitResult(BaseModel):
    total: int
    correct: int
    accuracy: float
    items: list[QuizResultItem]


# ---------------------------------------------------------------------------
# 闪卡与复习
# ---------------------------------------------------------------------------


class FlashcardCreate(BaseModel):
    course_id: str
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)


class FlashcardFromQuiz(BaseModel):
    """错题转卡：题目 id 即可，内容从题目生成。"""

    question_id: int


class FsrsState(BaseModel):
    """前端 ts-fsrs 计算后的调度状态（前端计算、后端存储）。"""

    due: dt.datetime
    stability: float = 0.0
    difficulty: float = 0.0
    state: int = 0
    reps: int = 0
    lapses: int = 0
    last_review: dt.datetime | None = None
    rating: int  # 本次评分（写 review_logs 用）
    scheduled_days: float = 0.0
    elapsed_days: float = 0.0


class FlashcardOut(BaseModel):
    id: str
    course_id: str
    front: str
    back: str
    origin: str
    origin_question_id: int | None
    due: dt.datetime
    stability: float
    difficulty: float
    state: int
    reps: int
    lapses: int
    last_review: dt.datetime | None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# 复习计划
# ---------------------------------------------------------------------------


class SprintPlanCreate(BaseModel):
    """冲刺计划：考试日期 + 每日时间预算。"""

    course_id: str
    exam_date: dt.date
    daily_budget_minutes: int = Field(ge=10, le=480)


class ManualPlanCreate(BaseModel):
    """手动计划：范围 + 每日卡量 + 天数。"""

    course_id: str
    only_wrong: bool = False
    daily_card_count: int = Field(ge=5, le=200)
    days: int = Field(ge=1, le=30)


class PlanDayOut(BaseModel):
    date: str
    card_ids: list[str]
    est_minutes: float
    # 后端生成的可解释依据；前端用于“计划依据”展开区。
    reason: str = "按你设定的每日学习量顺序安排"


class ReviewPlanOut(BaseModel):
    id: str
    course_id: str
    mode: str
    exam_date: dt.date | None
    daily_budget_minutes: int | None
    scope: dict
    plan_days: list[PlanDayOut]
    status: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class StatsOut(BaseModel):
    course_id: str
    total_cards: int
    due_today: int
    reviewed_today: int
    total_attempts: int
    correct_rate: float
    streak_days: int
    last_7_days: list[dict]  # [{date, reviewed, due}]
