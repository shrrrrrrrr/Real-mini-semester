"""航友后端入口：FastAPI 应用工厂。

本地优先架构（无云依赖）：
- SQLite 单文件主存储 + 本地原件目录；
- 仅 LLM 走云端 API（OpenAI 兼容协议，供应商可配置）。
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import books, chat, documents, explain, flashcards, profile, quiz, review_plans, stats, tasks
from app.config import settings
from app.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    init_db()  # 幂等建表

    # 主线程预加载嵌入模型：规避 torch 在子线程首次加载的死锁问题
    # （失败不阻断启动：无网络时上传文件会标记 failed，服务仍可用）
    try:
        from app.core.retrieval import warmup_embedder

        warmup_embedder()
    except Exception as e:  # pragma: no cover - 环境问题不阻断服务
        logging.getLogger(__name__).warning("嵌入模型预热失败（离线？）：%s", e)

    app = FastAPI(
        title="航友 API",
        description="面向大学生的课程资料智能问答与复习系统（本地优先）",
        version="1.0.0",
    )

    # CORS：开发期前端 Vite 端口（生产同源部署则不触发）
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(documents.router, prefix="/api")
    app.include_router(books.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(explain.router, prefix="/api")
    app.include_router(quiz.router, prefix="/api")
    app.include_router(flashcards.router, prefix="/api")
    app.include_router(review_plans.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        """健康检查：前端启动时探测后端是否在线。"""
        return {"ok": True, "llm_configured": bool(settings.llm_api_key)}

    return app


app = create_app()
