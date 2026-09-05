"""闪卡与复习接口：错题转卡 / 手动建卡 / 到期查询 / 评分状态同步。"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404
from app.api_schemas import (
    FlashcardCreate,
    FlashcardFromQuiz,
    FlashcardOut,
    FsrsState,
)
from app.db import get_db
from app.models import Flashcard, QuizQuestion, ReviewLog

router = APIRouter()


@router.post("/flashcards")
def create_flashcard(body: FlashcardCreate, db: Session = Depends(get_db)):
    """手动建卡：新卡 due=now（打开复习页即会出现）。"""
    get_course_or_404(db, body.course_id)
    card = Flashcard(
        id=uuid.uuid4().hex,
        course_id=body.course_id,
        front=body.front.strip(),
        back=body.back.strip(),
        origin="manual",
        due=dt.datetime.now(dt.timezone.utc),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.post("/flashcards/from-quiz")
def create_from_quiz(body: FlashcardFromQuiz, db: Session = Depends(get_db)):
    """错题转卡：正面 = 题干，背面 = 正确答案 + 解析。

    唯一约束（course_id + origin_question_id）防止同一题重复转卡。
    """
    q = db.get(QuizQuestion, body.question_id)
    if q is None:
        raise HTTPException(404, "题目不存在")
    exists = db.scalar(
        select(Flashcard).where(Flashcard.origin_question_id == q.id)
    )
    if exists:
        raise HTTPException(400, "该错题已转过闪卡")

    letters = ["A", "B", "C", "D"]
    correct_text = (
        f"{q.answer}. {q.options[letters.index(q.answer)]}" if len(q.options) == 4 else q.answer
    )
    card = Flashcard(
        id=uuid.uuid4().hex,
        course_id=q.quiz.course_id,
        front=q.stem,
        back=f"正确答案：{correct_text}\n\n解析：{q.explanation}",
        origin="quiz",
        origin_question_id=q.id,
        due=dt.datetime.now(dt.timezone.utc),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.get("/courses/{course_id}/flashcards", response_model=list[FlashcardOut])
def list_flashcards(course_id: str, db: Session = Depends(get_db)):
    """课程全部闪卡（前端按 due 过滤到期队列 + 积压合并）。"""
    get_course_or_404(db, course_id)
    return db.scalars(
        select(Flashcard)
        .where(Flashcard.course_id == course_id)
        .order_by(Flashcard.due)
    ).all()


@router.get("/flashcards/due", response_model=list[FlashcardOut])
def due_flashcards(course_id: str, db: Session = Depends(get_db)):
    """到期卡片查询（备用轻量接口，主流程由前端拉全量再过滤）。"""
    get_course_or_404(db, course_id)
    now = dt.datetime.now(dt.timezone.utc)
    return db.scalars(
        select(Flashcard)
        .where(Flashcard.course_id == course_id, Flashcard.due <= now)
        .order_by(Flashcard.due)
    ).all()


@router.patch("/flashcards/{card_id}", response_model=FlashcardOut)
def sync_flashcard(card_id: str, body: FsrsState, db: Session = Depends(get_db)):
    """评分状态同步：前端 ts-fsrs 计算的新状态整体落库 + 写复习日志。

    架构约定：前端计算、后端存储、以服务器数据为准。
    """
    card = db.get(Flashcard, card_id)
    if card is None:
        raise HTTPException(404, "闪卡不存在")

    card.due = body.due
    card.stability = body.stability
    card.difficulty = body.difficulty
    card.state = body.state
    card.reps = body.reps
    card.lapses = body.lapses
    card.last_review = body.last_review

    # 复习日志：原始评分记录（统计分析与后续 FSRS 参数优化的数据基础）
    db.add(
        ReviewLog(
            flashcard_id=card.id,
            rating=body.rating,
            review_time=dt.datetime.now(dt.timezone.utc),
            scheduled_days=body.scheduled_days,
            elapsed_days=body.elapsed_days,
        )
    )
    db.commit()
    db.refresh(card)
    return card


@router.delete("/flashcards/{card_id}", status_code=204)
def delete_flashcard(card_id: str, db: Session = Depends(get_db)):
    card = db.get(Flashcard, card_id)
    if card is None:
        raise HTTPException(404, "闪卡不存在")
    db.delete(card)
    db.commit()
