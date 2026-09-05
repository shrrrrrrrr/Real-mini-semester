"""复习计划接口：冲刺模式（考试日期+预算）/ 手动模式（范围+每日卡量）。

排程算法在前端（src/lib/reviewPlan.ts）计算后提交；本接口负责
持久化与"同课程仅一个 active 计划"的约束。为支持无前端算法的调用方
（如测试），此处也内置同款排程逻辑（后端独立实现一份，两端可交叉验证）。
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404
from app.api_schemas import ManualPlanCreate, ReviewPlanOut, SprintPlanCreate
from app.db import get_db
from app.models import Flashcard, ReviewPlan

router = APIRouter()

AVG_CARD_SECONDS = 12  # 单卡平均耗时（秒），与前端常量保持一致


def _urgency(card: Flashcard, today: dt.date, exam_date: dt.date) -> float:
    """紧迫度：到期临近 × 低稳定性 × 错题来源（与前端同权重）。"""
    days_to_exam = max(1, (exam_date - today).days)
    due_date = card.due.date()
    due_proximity = (
        1.0 if due_date <= today else max(0.0, 1 - (due_date - today).days / days_to_exam)
    )
    return (
        0.4 * due_proximity
        + 0.4 * (1 - min(1.0, card.stability / 30))
        + 0.2 * (1.0 if card.origin == "quiz" else 0.0)
    )


def _plan_reason(cards: list[Flashcard], target_date: dt.date, exam_date: dt.date | None) -> str:
    """把排程依据转成用户可核对的短句，避免计划像黑箱。"""
    reasons: list[str] = []
    wrong_count = sum(card.origin == "quiz" for card in cards)
    weak_count = sum(card.stability < 10 for card in cards)
    due_count = sum(card.due.date() <= target_date for card in cards)
    if wrong_count:
        reasons.append(f"优先巩固 {wrong_count} 张测验错题")
    if weak_count:
        reasons.append(f"复习 {weak_count} 张掌握度较低的卡")
    if due_count:
        reasons.append(f"处理 {due_count} 张已到期或临近到期的卡")
    if exam_date is not None:
        days_left = max(0, (exam_date - target_date).days)
        reasons.append(f"距离考试还有 {days_left} 天")
    return "；".join(reasons) or "按你设定的每日学习量顺序安排"


def _chunk_days(
    cards: list[Flashcard], per_day: int, days_limit: int, today: dt.date, exam_date: dt.date | None = None
):
    """按序切分逐日队列，并把错题、到期与考试倒计时写入计划依据。"""
    out = []
    for i in range(0, min(len(cards), per_day * days_limit), per_day):
        day_cards = cards[i : i + per_day]
        target_date = today + dt.timedelta(days=len(out))
        out.append(
            {
                "date": target_date.isoformat(),
                "card_ids": [c.id for c in day_cards],
                "est_minutes": round(len(day_cards) * AVG_CARD_SECONDS / 60),
                "reason": _plan_reason(day_cards, target_date, exam_date),
            }
        )
    return [{"date": today.isoformat(), "card_ids": [], "est_minutes": 0, "reason": "当前范围内没有可安排的卡片"}] if not out else out


def _deactivate_plans(db: Session, course_id: str) -> None:
    """同课程仅一个 active 计划：新建前归档旧计划。"""
    for p in db.scalars(
        select(ReviewPlan).where(
            ReviewPlan.course_id == course_id, ReviewPlan.status == "active"
        )
    ):
        p.status = "archived"


@router.post("/review-plans/sprint", response_model=ReviewPlanOut)
def create_sprint_plan(body: SprintPlanCreate, db: Session = Depends(get_db)):
    """冲刺计划：考试日期 + 每日分钟预算 → 紧迫度重排 + 脆弱卡考前 48h 二刷。"""
    get_course_or_404(db, body.course_id)
    today = dt.date.today()
    if body.exam_date <= today:
        raise HTTPException(400, "考试日期必须在未来")

    cards = db.scalars(
        select(Flashcard).where(Flashcard.course_id == body.course_id)
    ).all()
    if not cards:
        raise HTTPException(400, "该课程还没有闪卡，先做一套测验并转错题卡")

    days_limit = (body.exam_date - today).days
    per_day = max(10, (body.daily_budget_minutes * 60) // AVG_CARD_SECONDS)

    # 按紧迫度降序排列（错题卡 > 低稳定性卡 > 其他）
    ranked = sorted(cards, key=lambda c: _urgency(c, today, body.exam_date), reverse=True)

    plan_days = _chunk_days(ranked, per_day, days_limit, today, body.exam_date)

    # 脆弱卡（紧迫度前 30%）考前 48h 二刷：追加到最后两天的其中一天
    fragile = ranked[: max(1, len(ranked) * 3 // 10)]
    second_idx = max(0, len(plan_days) - 2)
    for c in fragile:
        in_last_two = any(
            c.id in d["card_ids"] for d in plan_days[-2:]
        )
        if not in_last_two:
            plan_days[second_idx]["card_ids"].append(c.id)

    _deactivate_plans(db, body.course_id)
    plan = ReviewPlan(
        id=uuid.uuid4().hex,
        course_id=body.course_id,
        mode="sprint",
        exam_date=body.exam_date,
        daily_budget_minutes=body.daily_budget_minutes,
        scope={},
        plan_days=plan_days,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/review-plans/manual", response_model=ReviewPlanOut)
def create_manual_plan(body: ManualPlanCreate, db: Session = Depends(get_db)):
    """手动计划：范围（仅错题/全部）+ 每日卡量 + 天数。"""
    get_course_or_404(db, body.course_id)
    cards = db.scalars(
        select(Flashcard)
        .where(Flashcard.course_id == body.course_id)
        .order_by(Flashcard.due)
    ).all()
    if body.only_wrong:
        cards = [c for c in cards if c.origin == "quiz"]
    if not cards:
        raise HTTPException(400, "范围内没有闪卡")

    today = dt.date.today()
    plan_days = _chunk_days(cards, body.daily_card_count, body.days, today)

    _deactivate_plans(db, body.course_id)
    plan = ReviewPlan(
        id=uuid.uuid4().hex,
        course_id=body.course_id,
        mode="manual",
        scope={"only_wrong": body.only_wrong},
        plan_days=plan_days,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/courses/{course_id}/review-plans/active", response_model=ReviewPlanOut | None)
def get_active_plan(course_id: str, db: Session = Depends(get_db)):
    """当前活动计划（无则返回 null）。"""
    get_course_or_404(db, course_id)
    plan = db.scalar(
        select(ReviewPlan).where(
            ReviewPlan.course_id == course_id, ReviewPlan.status == "active"
        )
    )
    return plan


@router.delete("/review-plans/{plan_id}", status_code=204)
def archive_plan(plan_id: str, db: Session = Depends(get_db)):
    """归档计划（回到长期 FSRS 模式）。"""
    plan = db.get(ReviewPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "计划不存在")
    plan.status = "archived"
    db.commit()
