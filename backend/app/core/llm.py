"""LLM 客户端：OpenAI 兼容协议封装。

配置优先级（用户确认的"我的"页设置）：
用户配置（SQLite user_profile）> backend/.env 环境变量。
所有调用方传 db 会话，读取生效配置；无 db 时回落 .env。

能力：
- chat_stream / chat_json：对话（流式 / JSON mode）；
- generate_structured：结构化输出（契约 + Pydantic 校验 + 定向重试）。

供应商中立：换 DeepSeek / GLM / Qwen / OpenAI 只需改配置。
"""

import json
from collections.abc import AsyncIterator
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """LLM 调用失败（网络/鉴权/模型错误）。"""


class LLMFormatError(LLMError):
    """结构化输出经重试后仍不合规（宁缺毋滥，向上抛错）。"""


def llm_config_effective(db=None) -> dict:
    """只读取“我的”页保存的 LLM 配置，不再回退到 backend/.env。

    这样用户能明确知道当前由哪套 API 配置付费和回答；缺任一项时，
    调用方统一提示到“我的”页设置，而不是悄悄使用历史环境变量。
    """
    empty = {"base_url": None, "api_key": None, "model": None}
    if db is None:
        return empty
    try:
        from app.models import UserProfile

        profile = db.get(UserProfile, 1)
        if profile is None:
            return empty
        return {
            "base_url": profile.llm_base_url,
            "api_key": profile.llm_api_key,
            "model": profile.llm_model,
        }
    except Exception:
        # 配置读取失败时宁可拒绝调用，也不能泄漏回退到旧环境配置。
        return empty


def _headers(cfg: dict) -> dict[str, str]:
    if not all((cfg["base_url"], cfg["api_key"], cfg["model"])):
        raise LLMError("请先在「我的 → AI 服务设置」填写接口地址、模型名和 API Key")
    return {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }


async def chat_stream(
    messages: list[dict],
    temperature: float = 0.3,
    db=None,
) -> AsyncIterator[str]:
    """流式对话：逐 token 产出文本片段（OpenAI 格式 messages）。"""
    cfg = llm_config_effective(db)
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    timeout = httpx.Timeout(120.0, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=_headers(cfg), json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "ignore")
                    raise LLMError(f"LLM 接口错误 {resp.status_code}: {body[:300]}")
                async for line in resp.aiter_lines():
                    # SSE 原始行：data: {...}；[DONE] 结束
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        token = delta.get("content")
                        if token:
                            yield token
    except httpx.HTTPError as e:
        raise LLMError(f"LLM 网络错误：{e}") from e


def _strip_json_fence(raw: str) -> str:
    """剥掉部分模型喜欢包裹的 ```json 代码围栏。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


async def chat_json(
    messages: list[dict],
    temperature: float = 0.3,
    db=None,
) -> str:
    """非流式 JSON 模式调用：返回模型输出的原始字符串。"""
    cfg = llm_config_effective(db)
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    return await _chat_request(cfg, payload)


async def chat_json_plain(
    messages: list[dict],
    temperature: float = 0.4,
    db=None,
) -> str:
    """非流式纯文本调用（无 JSON mode）：节点展开讲解等自由正文场景。"""
    cfg = llm_config_effective(db)
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
    }
    return await _chat_request(cfg, payload)


async def _chat_request(cfg: dict, payload: dict) -> str:
    """公共请求逻辑：POST chat/completions 并取 content。"""
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    timeout = httpx.Timeout(120.0, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=_headers(cfg), json=payload)
            if resp.status_code != 200:
                raise LLMError(
                    f"LLM 接口错误 {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            return (data["choices"][0]["message"]["content"] or "").strip()
    except httpx.HTTPError as e:
        raise LLMError(f"LLM 网络错误：{e}") from e
    except (KeyError, IndexError) as e:
        raise LLMError(f"LLM 响应结构异常：{e}") from e


async def generate_structured(
    messages: list[dict],
    schema: type[T],
    max_retries: int | None = None,
    temperature: float = 0.3,
    db=None,
) -> T:
    """结构化生成：JSON mode 输出 → Pydantic 校验 → 失败携带具体错误定向重试。

    核心思想（开发文档 §5.2 技术点②）：用类型系统约束 LLM 输出，
    非法枚举/字段缺失在进入业务层前被拦截。
    """
    if max_retries is None:
        max_retries = settings.llm_max_retries
    current = list(messages)
    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        raw = await chat_json(current, temperature=temperature, db=db)
        try:
            return schema.model_validate_json(_strip_json_fence(raw))
        except ValidationError as e:
            last_error = e
            # 定向重试：把校验错误原文反馈给模型，让它知道错在哪
            current = current + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": f"上次输出不合规，校验错误：{e}\n请严格按契约修正后重新输出完整 JSON。",
                },
            ]
    raise LLMFormatError(f"结构化输出校验失败（已重试 {max_retries} 次）: {last_error}")
