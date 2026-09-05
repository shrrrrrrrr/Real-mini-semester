"""测验接口：生成（后台任务，切页不中断）→ 提交判分 → 历史回看。

生成不中断：POST /quizzes 立即返回 task_id；LLM 后台出题落库，
前端轮询 GET /tasks/{task_id}；结果同时写入 gen_tasks.result。
answer 字段在生成结果与列表接口中均不返回（判分后才给）。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404, select_indexed_chunks
from app.api.tasks import finish_task, fail_task, spawn_task
from app.api_schemas import QuizCreate, QuizSubmit, QuizSubmitResult
from app.core import prompts
from app.core.llm import LLMError, generate_structured
from app.core.retrieval import build_course_index
from app.db import SessionLocal, get_db
from app.models import Quiz, QuizAttempt, QuizQuestion

router = APIRouter()


def _quiz_to_out(db: Session, quiz: Quiz, with_answer: bool = False) -> dict:
    """测验对象转响应（默认不含 answer，防泄露）。"""
    questions = db.scalars(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz.id)
        .order_by(QuizQuestion.question_no)
    ).all()
    q_list = []
    for q in questions:
        item = {
            "id": q.id,
            "question_no": q.question_no,
            "stem": q.stem,
            "options": q.options,
            "difficulty": q.difficulty,
        }
        if with_answer:
            item["answer"] = q.answer
            item["explanation"] = q.explanation
        q_list.append(item)
    return {
        "id": quiz.id,
        "course_id": quiz.course_id,
        "question_count": quiz.question_count,
        "created_at": quiz.created_at.isoformat(),
        "questions": q_list,
    }


def _generate_quiz_sync(task_id: str, course_id: str, count: int) -> None:
    """后台执行：检索课程资料 → LLM 结构化出题 → 落库。"""
    db = SessionLocal()
    try:
        chunks = select_indexed_chunks(db, course_id)
        if not chunks:
            fail_task(task_id, "该课程没有已就绪的资料，先去资料库上传并等待解析")
            return

        # 出题检索：轮转取样保证章节覆盖（题量 × 3 + 余量）
        take = min(len(chunks), count * 3)
        step = max(1, len(chunks) // take)
        sampled = chunks[::step][:take]
        context = prompts.build_context(sampled)

        messages = [
            {"role": "system", "content": prompts.QUIZ_SYSTEM},
            {
                "role": "user",
                "content": prompts.QUIZ_USER_TMPL.format(context=context, count=count),
            },
        ]
        try:
            import asyncio

            spec = asyncio.run(generate_structured(messages, prompts.QuizSpec, db=db))
        except LLMError as e:
            fail_task(task_id, f"出题失败：{e}")
            return

        questions = [
            q for q in spec.questions if len(q.options) == 4 and q.answer in "ABCD"
        ]
        if not questions:
            fail_task(task_id, "生成题目全部未通过校验，请重试")
            return

        quiz = Quiz(
            id=uuid.uuid4().hex, course_id=course_id, question_count=len(questions)
        )
        db.add(quiz)
        db.flush()
        for no, q in enumerate(questions, start=1):
            db.add(
                QuizQuestion(
                    quiz_id=quiz.id,
                    question_no=no,
                    stem=q.stem,
                    options=q.options,
                    answer=q.answer,
                    explanation=q.explanation,
                    difficulty=q.difficulty,
                )
            )
        db.commit()
        finish_task(task_id, _quiz_to_out(db, quiz))
    except Exception as e:
        fail_task(task_id, f"出题异常：{e}")
    finally:
        db.close()


@router.post("/quizzes")
async def create_quiz(body: QuizCreate, db: Session = Depends(get_db)):
    """创建测验生成任务：秒回 task_id，前端轮询取结果。"""
    get_course_or_404(db, body.course_id)
    task_id = spawn_task(
        "quiz",
        lambda tid: _generate_quiz_sync(tid, body.course_id, body.count),
        course_id=body.course_id,
        params={"count": body.count},
    )
    return {"task_id": task_id}


@router.post("/quizzes/{quiz_id}/submit", response_model=QuizSubmitResult)
def submit_quiz(quiz_id: str, body: QuizSubmit, db: Session = Depends(get_db)):
    """提交判分：逐题判对错 → 记录 attempts（正确率统计的数据来源）。"""
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "测验不存在")
    answers = {a.question_id: a.selected for a in body.answers}

    items = []
    correct = 0
    for q in db.scalars(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.question_no)
    ):
        selected = answers.get(q.id)
        if selected is None:
            continue  # 未作答的题跳过（前端已校验全部作答）
        is_correct = selected == q.answer
        if is_correct:
            correct += 1
        # 幂等：同一题重复提交只保留最后一次（先删旧记录）
        db.query(QuizAttempt).filter(
            QuizAttempt.question_id == q.id
        ).delete()
        db.add(
            QuizAttempt(
                question_id=q.id,
                quiz_id=quiz_id,
                selected=selected,
                is_correct=is_correct,
            )
        )
        items.append(
            {
                "question_id": q.id,
                "selected": selected,
                "answer": q.answer,
                "is_correct": is_correct,
                "explanation": q.explanation,
                "stem": q.stem,
                "options": q.options,
            }
        )
    db.commit()

    total = len(items)
    return QuizSubmitResult(
        total=total,
        correct=correct,
        accuracy=(correct / total) if total else 0.0,
        items=items,
    )


# ---------------------------------------------------------------------------
# 历史与回看（侧栏）
# ---------------------------------------------------------------------------


@router.get("/quizzes")
def list_quizzes(course_id: str, db: Session = Depends(get_db)):
    """测验历史列表（侧栏）：含题目数与是否已作答（有 attempts 即已提交）。"""
    get_course_or_404(db, course_id)
    quizzes = db.scalars(
        select(Quiz)
        .where(Quiz.course_id == course_id)
        .order_by(Quiz.created_at.desc())
        .limit(50)
    ).all()
    out = []
    for quiz in quizzes:
        attempted = db.scalar(
            select(QuizAttempt.id)
            .where(QuizAttempt.quiz_id == quiz.id)
            .limit(1)
        )
        out.append(
            {
                "id": quiz.id,
                "course_id": quiz.course_id,
                "question_count": quiz.question_count,
                "created_at": quiz.created_at.isoformat(),
                "attempted": attempted is not None,
            }
        )
    return out


@router.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: str, db: Session = Depends(get_db)):
    """测验详情回看：已提交的测验带 answer/explanation 与作答记录。"""
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "测验不存在")
    attempted = db.scalar(
        select(QuizAttempt.id).where(QuizAttempt.quiz_id == quiz_id).limit(1)
    )
    result = _quiz_to_out(db, quiz, with_answer=attempted is not None)
    if attempted is not None:
        # 附上最后一次作答选择（回看勾选状态）
        for a in db.scalars(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz_id)):
            for q in result["questions"]:
                if q["id"] == a.question_id:
                    q["selected"] = a.selected
                    q["is_correct"] = a.is_correct
    result["attempted"] = attempted is not None
    return result


@router.delete("/quizzes/{quiz_id}", status_code=204)
def delete_quiz(quiz_id: str, db: Session = Depends(get_db)):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "测验不存在")
    db.delete(quiz)
    db.commit()
