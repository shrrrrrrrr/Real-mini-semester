"""用户配置 API：昵称/头像/LLM 服务设置/教程状态。

单行表（id=1）本地存储。安全设计（答辩点）：
- API Key 明文存本地 SQLite：单机应用威胁模型即"能物理访问本机"，
  加密是形式主义；界面层脱敏展示（sk-***后4位）。
- 读取接口永不返回完整 Key；测试连接走真实 LLM 冒烟。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import GenTask, UserProfile

router = APIRouter()


def get_profile(db: Session) -> UserProfile:
    """取单行配置（无则惰性创建）。"""
    profile = db.get(UserProfile, 1)
    if profile is None:
        profile = UserProfile(id=1, nickname="学习者")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


class ProfileIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=40)
    avatar: str | None = None  # JPEG base64（前端 Canvas 压缩至 96×96）
    llm_base_url: str | None = None
    llm_api_key: str | None = None  # 空 = 不修改；"__clear__" = 清除
    llm_model: str | None = None


class ProfileOut(BaseModel):
    nickname: str
    avatar: str | None
    llm_base_url: str | None
    llm_model: str | None
    llm_key_hint: str | None  # 脱敏：sk-***abcd
    onboarding_done: bool


def key_hint(key: str | None) -> str | None:
    if not key:
        return None
    return f"sk-***{key[-4:]}" if len(key) > 8 else "sk-***"


@router.get("/profile", response_model=ProfileOut)
def read_profile(db: Session = Depends(get_db)):
    p = get_profile(db)
    return ProfileOut(
        nickname=p.nickname,
        avatar=p.avatar,
        llm_base_url=p.llm_base_url,
        llm_model=p.llm_model,
        llm_key_hint=key_hint(p.llm_api_key),
        onboarding_done=p.onboarding_done,
    )


@router.patch("/profile", response_model=ProfileOut)
def update_profile(body: ProfileIn, db: Session = Depends(get_db)):
    """部分更新：null 字段不动；llm_api_key 空串不动、__clear__ 清除。"""
    p = get_profile(db)
    if body.nickname is not None:
        p.nickname = body.nickname.strip() or "学习者"
    if body.avatar is not None:
        # base64 大小防御：压缩后约 10-30KB，上限 200KB 兜底
        if len(body.avatar) > 200 * 1024:
            raise HTTPException(400, "头像数据过大（>200KB），请重新选择")
        p.avatar = body.avatar if body.avatar else None
    if body.llm_base_url is not None:
        p.llm_base_url = body.llm_base_url.strip() or None
    if body.llm_model is not None:
        p.llm_model = body.llm_model.strip() or None
    if body.llm_api_key is not None:
        if body.llm_api_key == "__clear__":
            p.llm_api_key = None
        elif body.llm_api_key.strip():
            p.llm_api_key = body.llm_api_key.strip()
    db.commit()
    db.refresh(p)
    return ProfileOut(
        nickname=p.nickname,
        avatar=p.avatar,
        llm_base_url=p.llm_base_url,
        llm_model=p.llm_model,
        llm_key_hint=key_hint(p.llm_api_key),
        onboarding_done=p.onboarding_done,
    )


@router.post("/profile/llm-test")
async def test_llm_connection(db: Session = Depends(get_db)):
    """测试“我的”页保存的配置；缺项时不回退到 .env。"""
    from app.core.llm import llm_config_effective, chat_json

    effective = llm_config_effective(db)
    if not all((effective["base_url"], effective["api_key"], effective["model"])):
        raise HTTPException(400, "请先填写接口地址、模型名和 API Key")
    try:
        raw = await chat_json(
            [{"role": "user", "content": "输出 JSON: {\"ok\": true}"}],
            db=db,
        )
        return {"ok": True, "model": effective["model"], "response": raw[:80]}
    except Exception as e:
        raise HTTPException(400, f"连接失败：{e}")


@router.patch("/profile/onboarding")
def set_onboarding(done: bool, db: Session = Depends(get_db)):
    p = get_profile(db)
    p.onboarding_done = done
    db.commit()
    return {"ok": True}
