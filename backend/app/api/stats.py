"""统计接口：正确率 / 到期与已复习 / 连续天数 / 近 7 日热力图数据。"""

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404
from app.db import get_db
from app.models import Flashcard, Quiz, QuizAttempt, QuizQuestion, ReviewLog

router = APIRouter()


def _reviewed_on(db: Session, course_id: str, day: dt.date) -> int:
    """某日该课程的复习次数（review_logs JOIN flashcards 过滤课程）。"""
    return (
        db.scalar(
            select(func.count())
            .select_from(ReviewLog)
            .join(Flashcard, ReviewLog.flashcard_id == Flashcard.id)
            .where(
                Flashcard.course_id == course_id,
                func.date(ReviewLog.review_time) == day,
            )
        )
        or 0
    )


def _attempt_stats(db: Session, course_id: str) -> tuple[int, int]:
    """该课程全部答题的（总数, 正确数）：quiz → attempts 链路过滤。"""
    rows = db.execute(
        select(QuizAttempt.is_correct, func.count())
        .select_from(QuizAttempt)
        .join(QuizQuestion, QuizAttempt.question_id == QuizQuestion.id)
        .join(Quiz, QuizQuestion.quiz_id == Quiz.id)
        .where(Quiz.course_id == course_id)
        .group_by(QuizAttempt.is_correct)
    ).all()
    total = sum(n for _, n in rows)
    correct = sum(n for ok, n in rows if ok)
    return total, correct


@router.get("/courses/{course_id}/stats")
def course_stats(course_id: str, db: Session = Depends(get_db)):
    """课程级学习统计（统计看板的数据源）。"""
    get_course_or_404(db, course_id)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()

    total_cards = (
        db.scalar(select(func.count()).where(Flashcard.course_id == course_id)) or 0
    )
    due_today = (
        db.scalar(
            select(func.count()).where(
                and_(Flashcard.course_id == course_id, Flashcard.due <= now)
            )
        )
        or 0
    )
    reviewed_today = _reviewed_on(db, course_id, today)

    total_answers, correct_answers = _attempt_stats(db, course_id)

    # 连续学习天数：从今天往前数每天都有 review_log 的连续长度
    # （一次查询取全部复习日期集合，避免 365 次循环查询）
    days_with_logs = set(
        db.scalars(
            select(func.date(ReviewLog.review_time))
            .select_from(ReviewLog)
            .join(Flashcard, ReviewLog.flashcard_id == Flashcard.id)
            .where(Flashcard.course_id == course_id)
        )
    )
    streak = 0
    day = today
    while day in days_with_logs:
        streak += 1
        day -= dt.timedelta(days=1)

    # 近 7 日热力图
    last_7 = []
    for i in range(6, -1, -1):
        d = today - dt.timedelta(days=i)
        reviewed = _reviewed_on(db, course_id, d)
        due = (
            db.scalar(
                select(func.count()).where(
                    and_(
                        Flashcard.course_id == course_id,
                        func.date(Flashcard.due) == d,
                    )
                )
            )
            or 0
        )
        last_7.append({"date": d.isoformat(), "reviewed": reviewed, "due": due})

    return {
        "course_id": course_id,
        "total_cards": total_cards,
        "due_today": due_today,
        "reviewed_today": reviewed_today,
        "total_attempts": total_answers,
        "correct_rate": (correct_answers / total_answers) if total_answers else 0.0,
        "streak_days": streak,
        "last_7_days": last_7,
    }
