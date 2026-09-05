"""测验接口：从资料生成 MCQ（仅资料内容出题）→ 提交判分。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404, select_indexed_chunks
from app.api_schemas import QuizCreate, QuizSubmit, QuizSubmitResult
from app.core import prompts
from app.core.llm import LLMError, generate_structured
from app.core.retrieval import build_course_index
from app.db import get_db
from app.models import Quiz, QuizAttempt, QuizQuestion

router = APIRouter()


@router.post("/quizzes")
async def create_quiz(body: QuizCreate, db: Session = Depends(get_db)):
    """生成测验：检索课程资料 → LLM 结构化出题（QuizSpec 契约校验）。

    注意：answer 字段不返回前端（防止答案泄露），判分后才给。
    """
    get_course_or_404(db, body.course_id)
    chunks = select_indexed_chunks(db, body.course_id)
    if not chunks:
        raise HTTPException(400, "该课程没有已就绪的资料，先去资料库上传并等待解析")

    # 出题检索：多取几路片段保证覆盖面（题目量 × 每题 2 片段 + 余量）
    index = build_course_index(chunks)
    # 用空查询拿全部太粗；改为多锚点检索——按资料顺序轮转取样保证章节覆盖
    pool = chunks
    take = min(len(pool), body.count * 3)
    # 轮转取样：跨越不同文档/章节，避免题目扎堆在同一处
    step = max(1, len(pool) // take)
    sampled = pool[::step][:take]
    context = prompts.build_context(sampled)

    messages = [
        {"role": "system", "content": prompts.QUIZ_SYSTEM},
        {
            "role": "user",
            "content": prompts.QUIZ_USER_TMPL.format(context=context, count=body.count),
        },
    ]
    try:
        spec = await generate_structured(messages, prompts.QuizSpec)
    except LLMError as e:
        raise HTTPException(502, f"出题失败：{e}") from e

    questions = [
        q for q in spec.questions if len(q.options) == 4 and q.answer in "ABCD"
    ]
    if not questions:
        raise HTTPException(502, "生成题目全部未通过校验，请重试")

    quiz = Quiz(
        id=uuid.uuid4().hex, course_id=body.course_id, question_count=len(questions)
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
                source_chunk_ids=None,  # 题目级溯源（V1.5 可回填具体 chunk）
            )
        )
    db.commit()

    return {
        "id": quiz.id,
        "course_id": quiz.course_id,
        "question_count": quiz.question_count,
        "created_at": quiz.created_at,
        "questions": [
            {
                "id": q.id,
                "question_no": q.question_no,
                "stem": q.stem,
                "options": q.options,
                "difficulty": q.difficulty,
                # answer 有意不返回：判分前不泄露
            }
            for q in db.scalars(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz.id)
                .order_by(QuizQuestion.question_no)
            )
        ],
    }


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
