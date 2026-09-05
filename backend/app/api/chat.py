"""双层问答接口：检索 → LLM 分层生成 → SSE 流式返回。

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
这样前端渲染逻辑与真流式完全一致，未来切换到原生流式结构化输出无前端改动。
"""

import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import get_course_or_404, select_indexed_chunks
from app.api_schemas import ChatAsk
from app.core import prompts
from app.core.llm import LLMError, chat_stream
from app.core.retrieval import build_course_index
from app.db import get_db
from app.models import ChatSession, Message

router = APIRouter()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream_endpoint(body: ChatAsk, db: Session = Depends(get_db)):
    """双层问答主入口。"""
    get_course_or_404(db, body.course_id)

    # ---- 会话管理：无 session 则新建（标题 = 问题前 20 字）----
    if body.session_id:
        session = db.get(ChatSession, body.session_id)
        if session is None:
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

    # ---- 检索阶段（本地，毫秒级）----
    chunks = select_indexed_chunks(db, body.course_id)
    index = build_course_index(chunks)
    retrieved = index.retrieve(body.question)

    # 历史消息（最近 3 轮）
    history_msgs = db.scalars(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(6)
    ).all()
    history_msgs.reverse()

    # ---- 生成阶段：流式产出完整文本，再按契约切层 ----
    context = prompts.build_context(retrieved)
    history = prompts.build_history(history_msgs)
    user_prompt = prompts.QA_USER_TMPL.format(
        context=context if context else "（该课程暂无已就绪资料）",
        history=history,
        question=body.question,
    )

    # 先落用户消息
    user_msg = Message(
        session_id=session.id, role="user", content=body.question
    )
    db.add(user_msg)
    db.commit()

    async def event_stream():
        yield _sse({"type": "session", "session_id": session.id, "title": session.title})

        full_text = ""
        try:
            # 提示模型输出 JSON 契约（双层 segments）；流式收集全文
            messages = [
                {"role": "system", "content": prompts.QA_SYSTEM},
                {"role": "user", "content": user_prompt},
            ]
            async for token in chat_stream(messages, temperature=0.3):
                full_text += token

            # ---- 解析分层答案（容错：JSON 围栏剥除 + 降级）----
            segments = _parse_segments(full_text)
            for seg in segments:
                yield _sse({"type": "segment_start", "layer": seg["layer"]})
                # 分段文本按小块推送（前端渲染为逐段出现，视觉接近流式）
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

            # ---- 持久化助手消息（分层 + 引用）----
            assistant = Message(
                session_id=session.id,
                role="assistant",
                content="\n\n".join(s["text"] for s in segments),
                segments=segments,
                citations=citations,
            )
            db.add(assistant)
            db.commit()
            yield _sse({"type": "done", "message_id": assistant.id})
        except LLMError as e:
            # 网络未配置 / Key 无效等：写入失败占位消息，前端 toast 提示
            yield _sse({"type": "error", "detail": str(e)})
            db.add(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content=f"（回答失败：{e}）",
                    segments=[{"layer": "general", "text": f"回答失败：{e}"}],
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

    # 1) 直接解析
    try:
        spec = AnswerSpec.model_validate_json(text)
        return [{"layer": s.layer, "text": s.text.strip()} for s in spec.segments]
    except (ValidationError, ValueError):
        pass

    # 2) 提取最外层 {..}（部分模型会加前后说明文字）
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            spec = AnswerSpec.model_validate_json(text[start : end + 1])
            return [{"layer": s.layer, "text": s.text.strip()} for s in spec.segments]
        except (ValidationError, ValueError):
            pass

    # 3) 降级：全文作为 general 层（答案不丢，但明确标注非资料来源）
    return [{"layer": "general", "text": raw.strip()}]


# ---------------------------------------------------------------------------
# 会话查询接口（前端加载历史消息）
# ---------------------------------------------------------------------------


from fastapi import HTTPException  # noqa: E402


@router.get("/courses/{course_id}/sessions")
def list_sessions(course_id: str, db: Session = Depends(get_db)):
    get_course_or_404(db, course_id)
    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.course_id == course_id)
        .order_by(ChatSession.created_at.desc())
    ).all()
    return sessions


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(404, "会话不存在")
    msgs = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    ).all()
    return msgs


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(404, "会话不存在")
    db.delete(session)
    db.commit()
