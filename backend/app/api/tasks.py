"""后台生成任务 API：创建任务（秒回）→ 后台执行 → 前端轮询结果。

解决的问题（用户痛点）：生成讲解大纲/测验/节点讲解时切到别的页面，
生成不中断——LLM 在服务端跑完落库，回来轮询即见结果或进行中状态。
"""

import threading
import traceback

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, SessionLocal
from app.models import GenTask

router = APIRouter()


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    """轮询任务状态：pending/running/done/failed + 结果或错误。"""
    task = db.get(GenTask, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return {
        "id": task.id,
        "kind": task.kind,
        "context_id": task.context_id,
        "course_id": task.course_id,
        "status": task.status,
        "result": task.result,
        "failed_reason": task.failed_reason,
        "created_at": task.created_at,
        "finished_at": task.finished_at,
    }


def spawn_task(kind: str, runner, *, course_id=None, context_id=None, params=None) -> str:
    """创建并启动后台任务（通用入口，供 explain/quiz 路由调用）。

    runner(db_session, task_id) 为同步执行函数（内部自行开 DB 会话）；
    线程执行保证 HTTP 请求立即返回。
    """
    import uuid

    db = SessionLocal()
    try:
        task = GenTask(
            id=uuid.uuid4().hex,
            kind=kind,
            course_id=course_id,
            context_id=context_id,
            params=params or {},
        )
        db.add(task)
        db.commit()
        task_id = task.id
    finally:
        db.close()

    def _run():
        db2 = SessionLocal()
        try:
            t = db2.get(GenTask, task_id)
            t.status = "running"
            db2.commit()
        finally:
            db2.close()
        # runner 内部自行管理会话与状态落库（done/failed）
        try:
            runner(task_id)
        except Exception:
            # 兜底：runner 未捕获的异常也落 failed 状态
            db3 = SessionLocal()
            try:
                t = db3.get(GenTask, task_id)
                t.status = "failed"
                t.failed_reason = "任务内部异常"
                db3.commit()
            finally:
                db3.close()
            traceback.print_exc()

    threading.Thread(target=_run, daemon=True, name=f"gen-{task_id[:8]}").start()
    return task_id


def finish_task(task_id: str, result) -> None:
    """任务成功：结果落库（由 runner 调用）。"""
    db = SessionLocal()
    try:
        t = db.get(GenTask, task_id)
        t.result = result
        t.status = "done"
        import datetime as dt

        t.finished_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    finally:
        db.close()


def fail_task(task_id: str, reason: str) -> None:
    """任务失败：原因落库（由 runner 调用）。"""
    db = SessionLocal()
    try:
        t = db.get(GenTask, task_id)
        t.status = "failed"
        t.failed_reason = reason[:500]
        db.commit()
    finally:
        db.close()
