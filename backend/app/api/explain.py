"""讲解接口：大纲（后台任务生成）+ 节点展开讲解 + 历史列表 + 会话改名。

生成不中断设计：POST /explain/outline 立即返回 task_id（秒回），
LLM 在后台线程跑完落库（explains + gen_tasks.result），
前端切页不中断，回来轮询 GET /tasks/{task_id} 即见结果。
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404, select_indexed_chunks
from app.api.tasks import finish_task, fail_task, spawn_task
from app.core import prompts
from app.core.llm import LLMError, generate_structured
from app.core.retrieval import build_course_index
from app.db import get_db
from app.models import ChatSession, Document, Explain

router = APIRouter()


# ---------------------------------------------------------------------------
# 大纲生成（后台任务）
# ---------------------------------------------------------------------------


class OutlineCreate(BaseModel):
    course_id: str | None = None
    topic: str = Field(min_length=1, max_length=200)


def _outline_to_out(explain: Explain) -> dict:
    return {
        "id": explain.id,
        "course_id": explain.course_id,
        "topic": explain.topic,
        "sections": explain.outline,
        "node_contents": explain.node_contents,
        # ISO 字符串（可 JSON 序列化，前端直接展示）
        "created_at": explain.created_at.isoformat(),
    }


def _generate_outline_sync(task_id: str, course_id: str | None, topic: str) -> None:
    """后台执行：检索 → LLM 大纲（ExplainSpec 契约）→ 挂接片段 → 落库。"""
    db = SessionLocal()
    try:
        course_name = ""
        doc_list = "（无）"
        index = None
        if course_id:
            course = db.get(Course, course_id)
            if course:
                course_name = course.name
            docs = db.scalars(
                select(Document).where(
                    Document.course_id == course_id,
                    Document.status == "indexed",
                    Document.include_in_rag.is_(True),
                )
            ).all()
            if docs:
                doc_list = "\n".join(f"- {d.filename}（{d.chunk_count} 块）" for d in docs)
                chunks = select_indexed_chunks(db, course_id)
                index = build_course_index(chunks)

        messages = [
            {"role": "system", "content": prompts.EXPLAIN_SYSTEM},
            {
                "role": "user",
                "content": prompts.EXPLAIN_USER_TMPL.format(
                    course_name=course_name or "未指定",
                    doc_list=doc_list,
                    topic=topic,
                ),
            },
        ]
        try:
            spec = _run_async(generate_structured(messages, prompts.ExplainSpec, db=db))
        except LLMError as e:
            fail_task(task_id, f"大纲生成失败：{e}")
            return

        # 大纲结构转存储格式；同时做资料挂接检索
        sections_out = []
        for sec in spec.sections:
            nodes_out = []
            for node in sec.nodes:
                linked_ids: list[int] = []
                if index is not None:
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
            course_id=course_id,
            topic=topic,
            outline=sections_out,
        )
        db.add(explain)
        db.commit()
        finish_task(task_id, _outline_to_out(explain))
    except Exception as e:
        fail_task(task_id, f"大纲生成异常：{e}")
    finally:
        db.close()


def _run_async(coro):
    """后台线程中跑协程：独立事件循环执行并取结果。"""
    import asyncio

    return asyncio.run(coro)


@router.post("/explain/outline")
async def create_explain_task(body: OutlineCreate, db: Session = Depends(get_db)):
    """创建大纲生成任务：秒回 task_id，前端轮询取结果。"""
    if body.course_id:
        get_course_or_404(db, body.course_id)
    task_id = spawn_task(
        "explain",
        lambda tid: _generate_outline_sync(tid, body.course_id, body.topic.strip()),
        course_id=body.course_id,
        params={"topic": body.topic},
    )
    return {"task_id": task_id}


# ---------------------------------------------------------------------------
# 节点展开讲解（后台任务）：大纲过简 → 逐节点生成完整讲解正文
# ---------------------------------------------------------------------------


class NodeExpand(BaseModel):
    explain_id: str
    sec_index: int = Field(ge=0)
    node_index: int = Field(ge=0)


NODE_EXPAND_SYSTEM = """你是"知源"的讲解助手。针对给定的知识点，输出一段完整、循序渐进的讲解正文。

要求：
1. 直接输出讲解内容（非 JSON），使用 Markdown 纯文本；
2. 结构：概念定义 → 为什么需要它 → 工作原理（分步骤讲）→ 常见误区 → 一个具体例子；
3. 若课程资料片段与该知识点相关，优先采用资料口径（引用片段原句时注明"据资料"）；
4. 篇幅 300-600 字，语言与主题一致，面向大学初学者。"""


def _expand_node_sync(task_id: str, explain_id: str, sec_i: int, node_i: int) -> None:
    db = SessionLocal()
    try:
        explain = db.get(Explain, explain_id)
        if explain is None or sec_i >= len(explain.outline):
            fail_task(task_id, "大纲不存在")
            return
        sec = explain.outline[sec_i]
        node = sec["nodes"][node_i]

        # 挂接的资料片段作为讲解依据（若有）
        context = ""
        if node.get("linked_chunk_ids"):
            chunks = (
                db.query(Chunk)
                .filter(Chunk.id.in_(node["linked_chunk_ids"]))
                .all()
            )
            context = prompts.build_context(chunks)

        user = f"【课程资料片段】\n{context or '（无）'}\n\n【要讲解的知识点】{sec['title']} —— {node['title']}"
        try:
            from app.core.llm import chat_json_plain

            text = _run_async(
                chat_json_plain(
                    [
                        {"role": "system", "content": NODE_EXPAND_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    db=db,
                )
            )
        except LLMError as e:
            fail_task(task_id, f"讲解生成失败：{e}")
            return

        explain.node_contents = {**(explain.node_contents or {}), f"{sec_i}:{node_i}": text}
        db.commit()
        finish_task(task_id, {"key": f"{sec_i}:{node_i}", "content": text})
    except Exception as e:
        fail_task(task_id, f"讲解生成异常：{e}")
    finally:
        db.close()


@router.post("/explain/node-expand")
async def expand_node(body: NodeExpand, db: Session = Depends(get_db)):
    explain = db.get(Explain, body.explain_id)
    if explain is None:
        raise HTTPException(404, "大纲不存在")
    task_id = spawn_task(
        "explain_node",
        lambda tid: _expand_node_sync(tid, body.explain_id, body.sec_index, body.node_index),
        course_id=explain.course_id,
        context_id=explain.id,
    )
    return {"task_id": task_id}


# ---------------------------------------------------------------------------
# 历史与查询
# ---------------------------------------------------------------------------


@router.get("/explains")
def list_explains(course_id: str | None = None, db: Session = Depends(get_db)):
    """历史讲解大纲列表（侧栏回看）。"""
    q = select(Explain).order_by(Explain.created_at.desc()).limit(50)
    if course_id:
        q = q.where(Explain.course_id == course_id)
    return [_outline_to_out(e) for e in db.scalars(q)]


@router.get("/explains/{explain_id}")
def get_explain(explain_id: str, db: Session = Depends(get_db)):
    e = db.get(Explain, explain_id)
    if e is None:
        raise HTTPException(404, "大纲不存在")
    return _outline_to_out(e)


@router.delete("/explains/{explain_id}", status_code=204)
def delete_explain(explain_id: str, db: Session = Depends(get_db)):
    e = db.get(Explain, explain_id)
    if e is None:
        raise HTTPException(404, "大纲不存在")
    db.delete(e)
    db.commit()


# 导入放底部避免循环依赖（documents ↔ explain）
from app.db import SessionLocal  # noqa: E402
from app.models import Chunk, Course  # noqa: E402
