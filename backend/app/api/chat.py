"""双层问答接口：检索 → LLM 分层生成 → SSE 流式返回。

分支对话（树形结构）：
- 请求带 parent_message_id = 某条 assistant 消息 → 从该答案长出新分支；
- 分支上下文 = 根 → 该分支路径上的历史（互不污染）；
- GET /sessions/{id}/tree 返回问题树（浮层图渲染用）；
- user 消息支持 branch_name 重命名（浮层图右键）。

SSE 事件协议（与前端 src/lib/api.ts 对齐）：
  data: {"type":"session","session_id":...,"title":...}
  data: {"type":"segment_start","layer":"doc"|"general"}
  data: {"type":"token","text":"..."}          ← doc 层 token（黄底高亮）
  data: {"type":"citations","citations":[...]} ← 引用列表（后端原样取出，不经 LLM）
  data: {"type":"done","message_id":...}
  data: {"type":"error","detail":"..."}

实现策略（开发文档 §4.1 设计决策 3）：一次 LLM 调用产出 doc/general 分区
答案。结构化输出无法逐 token 流式，故采用"分层流式"折中：
  - 先流式调用生成完整答案（用户体验优先）；
  - 生成完成后按 segments 契约解析，逐段以 segment_start + 批量 token 事件推送；
  - 解析失败时降级为单 general 段（保证可用性）。
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404, select_indexed_chunks
from app.api_schemas import ChatAsk
from app.core import prompts
from app.core.llm import LLMError, chat_stream
from app.core.retrieval import build_course_index
from app.db import get_db
from app.models import Book, ChatSession, Message

router = APIRouter()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class ChatAskV2(BaseModel):
    """提问请求 V2：支持分支（parent_message_id）、仅资料模式与书库勾选。"""

    course_id: str
    session_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)
    parent_message_id: int | None = None  # 被追问的 assistant 消息（分支起点）
    docs_only: bool = False
    book_ids: list[str] = Field(default_factory=list)  # 书库勾选（并入检索范围）


def _branch_path_messages(db: Session, session_id: str, leaf_message_id: int | None) -> list[Message]:
    """取分支路径上的历史：从最新 user 消息沿 parent 链上溯到根。

    上下文原则：每个分支只携带"根 → 该分支路径"的对话，互不污染
    （用户确认的分支语义）。
    """
    path: list[Message] = []
    current_id = leaf_message_id
    while current_id is not None and len(path) < 12:  # 上限 6 轮
        msg = db.get(Message, current_id)
        if msg is None or msg.session_id != session_id:
            break
        path.append(msg)
        current_id = msg.parent_message_id
    path.reverse()
    return path


@router.post("/chat/stream")
async def chat_stream_endpoint(body: ChatAskV2, db: Session = Depends(get_db)):
    """双层问答主入口（支持分支与仅资料模式）。"""
    get_course_or_404(db, body.course_id)

    # ---- 会话管理 ----
    if body.session_id:
        session = db.get(ChatSession, body.session_id)
        if session is None or session.course_id != body.course_id:
            session = ChatSession(
                id=uuid.uuid4().hex, course_id=body.course_id, title=body.question[:20]
            )
            db.add(session)
            db.commit()
    else:
        session = ChatSession(
            id=uuid.uuid4().hex, course_id=body.course_id, title=body.question[:20]
        )
        db.add(session)
        db.commit()

    # ---- 分支校验：parent 必须是本会话的 assistant 消息 ----
    parent = None
    if body.parent_message_id is not None:
        parent = db.get(Message, body.parent_message_id)
        if parent is None or parent.session_id != session.id or parent.role != "assistant":
            raise HTTPException(400, "被追问的消息不存在或不属于当前会话")

    # ---- 分支路径历史（代替"最近 6 条"）----
    history_msgs: list[Message] = []
    if body.parent_message_id is not None:
        # parent 本身就是用户选中的 assistant 回答。沿它的 parent 链回溯，
        # 才能得到“根问题 → 当前回答”的完整上下文；不能查尚未创建的新 user 消息。
        history_msgs = _branch_path_messages(db, session.id, body.parent_message_id)
    else:
        # 主干提问：取主干（无 parent 的消息）最近几条
        trunk = db.scalars(
            select(Message)
            .where(
                Message.session_id == session.id,
                Message.parent_message_id.is_(None),
            )
            .order_by(Message.created_at.desc())
            .limit(6)
        ).all()
        history_msgs = list(reversed(trunk))

    # ---- 检索阶段（本地，毫秒级）----
    # 范围 = 课程勾选资料 + 书库勾选图书（RRF 融合不分来源）
    chunks = list(select_indexed_chunks(db, body.course_id))
    from app.api.documents import doc_names_map

    names = doc_names_map(db, body.course_id)
    if body.book_ids:
        from app.api.books import load_book_chunks

        book_chunks = load_book_chunks(db, body.book_ids)
        # 书名并入引用名映射（引用展示《书名》）
        titles = {b.id: b.title for b in db.query(Book).filter(Book.id.in_(body.book_ids)).all()}
        names.update(titles)
        index = build_course_index(chunks + list(book_chunks), doc_names=names)
    else:
        index = build_course_index(chunks, doc_names=names)
    retrieved = index.retrieve(body.question)

    # ---- 生成阶段 ----
    context = prompts.build_context(retrieved)
    history = prompts.build_history(history_msgs)
    user_prompt = prompts.QA_USER_TMPL.format(
        context=context if context else "（该课程暂无已就绪资料）",
        history=history,
        question=body.question,
    )

    # 用户消息落库（带分支关系）
    user_msg = Message(
        session_id=session.id,
        role="user",
        content=body.question,
        parent_message_id=body.parent_message_id,
    )
    db.add(user_msg)
    db.commit()

    system_prompt = prompts.QA_SYSTEM_DOCS_ONLY if body.docs_only else prompts.QA_SYSTEM

    async def event_stream():
        yield _sse({"type": "session", "session_id": session.id, "title": session.title})

        full_text = ""
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            async for token in chat_stream(messages, temperature=0.3, db=db):
                full_text += token

            # ---- 解析分层答案（容错：JSON 围栏剥除 + 降级）----
            segments = _parse_segments(full_text)
            if body.docs_only:
                # 仅资料模式兜底：过滤掉模型违规输出的 general 层
                segments = [s for s in segments if s["layer"] == "doc"] or [
                    {"layer": "doc", "text": "资料中未找到相关内容。"}
                ]
            for seg in segments:
                yield _sse({"type": "segment_start", "layer": seg["layer"]})
                text = seg["text"]
                for i in range(0, len(text), 24):
                    yield _sse({"type": "token", "text": text[i : i + 24]})

            # ---- 引用由后端原样组装（不经 LLM，杜绝编造页码）----
            citations = [
                {
                    "index": i,
                    "chunk_id": c.chunk_id,
                    "filename": c.filename,
                    "locator": c.locator,
                    "snippet": c.content[:200],
                }
                for i, c in enumerate(retrieved, start=1)
            ]
            yield _sse({"type": "citations", "citations": citations})

            # ---- 持久化助手消息（挂到 user 消息的分支链上）----
            assistant = Message(
                session_id=session.id,
                role="assistant",
                content="\n\n".join(s["text"] for s in segments),
                segments=segments,
                citations=citations,
                parent_message_id=user_msg.id,  # assistant 的 parent = 触发它的 user 消息
            )
            db.add(assistant)
            db.commit()
            yield _sse({"type": "done", "message_id": assistant.id})
        except LLMError as e:
            yield _sse({"type": "error", "detail": str(e)})
            db.add(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content=f"（回答失败：{e}）",
                    segments=[{"layer": "general", "text": f"回答失败：{e}"}],
                    parent_message_id=user_msg.id,
                )
            )
            db.commit()
        except Exception as e:  # 兜底：任何异常都转为 SSE error 事件
            yield _sse({"type": "error", "detail": f"内部错误：{e}"})

    return StreamingResponse(
        event_stream(), media_type="text/event-stream; charset=utf-8"
    )


def _parse_segments(raw: str) -> list[dict]:
    """把 LLM 输出解析为 segments 列表（容错降级链）。

    1. 剥代码围栏 → 解析 JSON → 校验 layer 枚举；
    2. 解析失败 → 尝试从文本中提取 JSON 部分；
    3. 仍失败 → 整段作为 general 层返回（保证可用性，不吞答案）。
    """
    from pydantic import ValidationError

    from app.core.prompts import AnswerSpec

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()

    try:
        spec = AnswerSpec.model_validate_json(text)
        return [{"layer": s.layer, "text": s.text.strip()} for s in spec.segments]
    except (ValidationError, ValueError):
        pass

    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            spec = AnswerSpec.model_validate_json(text[start : end + 1])
            return [{"layer": s.layer, "text": s.text.strip()} for s in spec.segments]
        except (ValidationError, ValueError):
            pass

    return [{"layer": "general", "text": raw.strip()}]


# ---------------------------------------------------------------------------
# 会话与分支管理
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/sessions")
def list_sessions(course_id: str, db: Session = Depends(get_db)):
    get_course_or_404(db, course_id)
    return db.scalars(
        select(ChatSession)
        .where(ChatSession.course_id == course_id)
        .order_by(ChatSession.created_at.desc())
    ).all()


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, db: Session = Depends(get_db)):
    """平铺消息列表（兼容旧渲染）：按时间序返回全部消息。"""
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(404, "会话不存在")
    msgs = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    ).all()
    return msgs


@router.get("/sessions/{session_id}/tree")
def session_tree(session_id: str, db: Session = Depends(get_db)):
    """返回逐条消息树：每个节点都是一条真实消息，边即 parent_message_id。

    这样导图与会话存储完全同构：用户消息可从 assistant 消息继续提问，
    assistant 消息则挂在触发它的 user 消息下。前端不再把一轮问答压成一个节点。
    """
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(404, "会话不存在")
    msgs = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    ).all()

    nodes = {
        message.id: {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "branch_name": message.branch_name,
            "parent_message_id": message.parent_message_id,
            "children": [],
        }
        for message in msgs
    }
    roots: list[dict] = []
    for message in msgs:
        node = nodes[message.id]
        parent = nodes.get(message.parent_message_id)
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    return {"session_id": session_id, "roots": roots}

@router.patch("/messages/{message_id}/rename")
def rename_branch(message_id: int, body: dict, db: Session = Depends(get_db)):
    """分支重命名（浮层图右键）：改 user 消息的 branch_name。"""
    msg = db.get(Message, message_id)
    if msg is None or msg.role != "user":
        raise HTTPException(404, "消息不存在或不可命名")
    name = str(body.get("branch_name", "")).strip()
    if not name or len(name) > 60:
        raise HTTPException(400, "分支名需为 1-60 字符")
    msg.branch_name = name
    db.commit()
    return {"id": msg.id, "branch_name": msg.branch_name}


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: dict, db: Session = Depends(get_db)):
    """会话重命名（左侧列表）。"""
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(404, "会话不存在")
    title = str(body.get("title", "")).strip()
    if not title or len(title) > 60:
        raise HTTPException(400, "标题需为 1-60 字符")
    session.title = title
    db.commit()
    return session


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(404, "会话不存在")
    db.delete(session)
    db.commit()