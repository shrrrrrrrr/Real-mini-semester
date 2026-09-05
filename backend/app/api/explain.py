"""讲解大纲接口：书名/学科/章节 → 结构化大纲（节点可挂接资料片段）。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404, select_indexed_chunks
from app.api_schemas import ExplainCreate
from app.core import prompts
from app.core.llm import LLMError, generate_structured
from app.core.retrieval import build_course_index
from app.db import get_db
from app.models import Document, Explain

router = APIRouter()


@router.post("/explain/outline")
async def create_explain(body: ExplainCreate, db: Session = Depends(get_db)):
    """生成讲解大纲：LLM 结构化输出（ExplainSpec 契约）+ 资料片段自动挂接。

    挂接逻辑：对每个 node 的 linked_hint 做一次混合检索，
    命中的 chunk_id 存入大纲，前端展示"你的资料相关片段"。
    """
    course_name = ""
    doc_list = "（无）"
    index = None
    if body.course_id:
        course = get_course_or_404(db, body.course_id)
        course_name = course.name
        docs = db.scalars(
            select(Document).where(
                Document.course_id == body.course_id,
                Document.status == "indexed",
                Document.include_in_rag.is_(True),
            )
        ).all()
        if docs:
            doc_list = "\n".join(f"- {d.filename}（{d.chunk_count} 块）" for d in docs)
            # 构建课程索引供挂接检索
            chunks = select_indexed_chunks(db, body.course_id)
            index = build_course_index(chunks)

    messages = [
        {"role": "system", "content": prompts.EXPLAIN_SYSTEM},
        {
            "role": "user",
            "content": prompts.EXPLAIN_USER_TMPL.format(
                course_name=course_name or "未指定",
                doc_list=doc_list,
                topic=body.topic,
            ),
        },
    ]
    try:
        spec = await generate_structured(messages, prompts.ExplainSpec)
    except LLMError as e:
        raise HTTPException(502, f"大纲生成失败：{e}") from e

    # 大纲结构转存储格式；同时做资料挂接检索
    sections_out = []
    for sec in spec.sections:
        nodes_out = []
        for node in sec.nodes:
            linked_ids: list[int] = []
            if index is not None:  # 有已就绪资料时做挂接检索
                hint = f"{sec.title} {node.title} {node.linked_hint}"
                hits = index.retrieve(hint, top_k=3)
                linked_ids = [h.chunk_id for h in hits]
            nodes_out.append(
                {
                    "title": node.title,
                    "summary": node.summary,
                    "linked_hint": node.linked_hint,
                    "linked_chunk_ids": linked_ids,
                }
            )
        sections_out.append({"title": sec.title, "nodes": nodes_out})

    explain = Explain(
        id=uuid.uuid4().hex,
        course_id=body.course_id,
        topic=body.topic,
        outline=sections_out,
    )
    db.add(explain)
    db.commit()

    return {
        "id": explain.id,
        "course_id": explain.course_id,
        "topic": explain.topic,
        "sections": sections_out,
        "created_at": explain.created_at,
    }


@router.get("/explains")
def list_explains(course_id: str | None = None, db: Session = Depends(get_db)):
    """历史讲解大纲列表。"""
    q = select(Explain).order_by(Explain.created_at.desc()).limit(50)
    if course_id:
        q = q.where(Explain.course_id == course_id)
    explains = db.scalars(q).all()
    return [
        {
            "id": e.id,
            "course_id": e.course_id,
            "topic": e.topic,
            "sections": e.outline,
            "created_at": e.created_at,
        }
        for e in explains
    ]
