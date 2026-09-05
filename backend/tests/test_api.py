"""接口测试：FastAPI TestClient（覆盖核心链路，不依赖 LLM——chat/quiz 的
LLM 调用打桩跳过；数据库用内存 SQLite，测试间相互隔离）。

嵌入模型不加载（跳过索引 embedding 的用例仅验证状态机与元数据）。
"""

import datetime as dt
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db, engine
from app.main import create_app
from app.models import Chunk, Course, Document, Flashcard, QuizAttempt, QuizQuestion, Quiz


@pytest.fixture(scope="module")
def client():
    """模块级 TestClient：建表一次，测试共用（每测试清理自己数据）。"""
    init_db()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cleanup():
    """测试数据清理：用例结束后删除本用例创建的实体。"""
    created_courses: list[str] = []
    yield created_courses
    db = SessionLocal()
    try:
        for cid in created_courses:
            course = db.get(Course, cid)
            if course:
                db.delete(course)
        db.commit()
    finally:
        db.close()


def make_course(client: TestClient, name="测试课程") -> str:
    resp = client.post("/api/courses", json={"name": name})
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 课程与资料
# ---------------------------------------------------------------------------


class TestCourses:
    def test_create_and_list(self, client, cleanup):
        cid = make_course(client, "接口测试课程A")
        cleanup.append(cid)
        names = [c["name"] for c in client.get("/api/courses").json()]
        assert "接口测试课程A" in names

    def test_delete_course_404_after(self, client):
        cid = make_course(client, "待删除课程")
        assert client.delete(f"/api/courses/{cid}").status_code == 204
        assert client.delete(f"/api/courses/{cid}").status_code == 404

    def test_upload_rejects_bad_format(self, client, cleanup):
        cid = make_course(client)
        cleanup.append(cid)
        resp = client.post(
            f"/api/courses/{cid}/documents",
            files={"file": ("virus.exe", b"bin", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_upload_txt_and_pending_status(self, client, cleanup):
        """TXT 上传：立即返回 201 + pending 状态（后台索引线程可能秒完成，
        但状态一定是五态之一且 locater_type=line）。"""
        cid = make_course(client)
        cleanup.append(cid)
        content = "红黑树是一种自平衡二叉查找树。\n\n插入节点染红以保持黑高。".encode("utf-8")
        resp = client.post(
            f"/api/courses/{cid}/documents",
            files={"file": ("rbtree.txt", io.BytesIO(content), "text/plain")},
        )
        assert resp.status_code == 201
        doc = resp.json()
        assert doc["file_type"] == "txt"
        assert doc["locator_type"] == "line"
        assert doc["status"] in {"pending", "parsing", "indexed"}


# ---------------------------------------------------------------------------
# 会话消息
# ---------------------------------------------------------------------------


class TestSessions:
    def test_session_messages_flow(self, client, cleanup):
        """空会话消息列表返回空数组（chat 流接口依赖 LLM，见 test_chat_stubs）。"""
        cid = make_course(client)
        cleanup.append(cid)
        sessions = client.get(f"/api/courses/{cid}/sessions").json()
        assert sessions == []

    def test_missing_session_404(self, client):
        assert client.get("/api/sessions/nonexistent/messages").status_code == 404


# ---------------------------------------------------------------------------
# 闪卡与复习
# ---------------------------------------------------------------------------


class TestFlashcards:
    def test_manual_create_and_due(self, client, cleanup):
        cid = make_course(client)
        cleanup.append(cid)
        resp = client.post(
            "/api/flashcards",
            json={"course_id": cid, "front": "什么是红黑树？", "back": "自平衡二叉查找树"},
        )
        assert resp.status_code == 200
        card_id = resp.json()["id"]
        due = client.get(f"/api/flashcards/due?course_id={cid}").json()
        assert any(c["id"] == card_id for c in due)

    def test_sync_rating_state(self, client, cleanup):
        """评分状态同步：新状态落库 + review_logs 写入。"""
        cid = make_course(client)
        cleanup.append(cid)
        card = client.post(
            "/api/flashcards",
            json={"course_id": cid, "front": "F", "back": "B"},
        ).json()
        now = dt.datetime.now(dt.timezone.utc)
        resp = client.patch(
            f"/api/flashcards/{card['id']}",
            json={
                "due": now.isoformat(),
                "stability": 3.5,
                "difficulty": 5.0,
                "state": 2,
                "reps": 1,
                "lapses": 0,
                "last_review": now.isoformat(),
                "rating": 3,
                "scheduled_days": 3.0,
                "elapsed_days": 0.0,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["stability"] == 3.5
        assert resp.json()["state"] == 2

    def test_from_quiz_duplicate_rejected(self, client, cleanup):
        """错题转卡幂等性：同题重复转卡返回 400。"""
        cid = make_course(client)
        cleanup.append(cid)
        db = SessionLocal()
        try:
            quiz = Quiz(id=uuid.uuid4().hex, course_id=cid, question_count=1)
            db.add(quiz)
            db.flush()
            q = QuizQuestion(
                quiz_id=quiz.id,
                question_no=1,
                stem="题干为八个字符以上？",
                options=["甲", "乙", "丙", "丁"],
                answer="A",
                explanation="解析内容至少十个字符",
                difficulty="基础",
            )
            db.add(q)
            db.commit()
            qid = q.id
        finally:
            db.close()
        assert client.post("/api/flashcards/from-quiz", json={"question_id": qid}).status_code == 200
        dup = client.post("/api/flashcards/from-quiz", json={"question_id": qid})
        assert dup.status_code == 400
        assert "已转" in dup.json()["detail"]


# ---------------------------------------------------------------------------
# 复习计划
# ---------------------------------------------------------------------------


class TestReviewPlans:
    def test_sprint_plan_creation(self, client, cleanup):
        cid = make_course(client)
        cleanup.append(cid)
        # 先造卡
        for i in range(12):
            client.post(
                "/api/flashcards",
                json={"course_id": cid, "front": f"问题{i}", "back": f"答案{i}"},
            )
        exam = (dt.date.today() + dt.timedelta(days=3)).isoformat()
        resp = client.post(
            "/api/review-plans/sprint",
            json={"course_id": cid, "exam_date": exam, "daily_budget_minutes": 30},
        )
        assert resp.status_code == 200
        plan = resp.json()
        assert plan["mode"] == "sprint"
        assert len(plan["plan_days"]) >= 1
        # 逐日卡片总量应覆盖全部 12 张卡（三日计划）
        total_cards = sum(len(d["card_ids"]) for d in plan["plan_days"])
        assert total_cards >= 12

    def test_sprint_plan_past_date_rejected(self, client, cleanup):
        cid = make_course(client)
        cleanup.append(cid)
        client.post("/api/flashcards", json={"course_id": cid, "front": "F", "back": "B"})
        resp = client.post(
            "/api/review-plans/sprint",
            json={
                "course_id": cid,
                "exam_date": "2020-01-01",
                "daily_budget_minutes": 30,
            },
        )
        assert resp.status_code == 400

    def test_active_plan_singleton(self, client, cleanup):
        """同课程同时只有一个 active 计划：新建即归档旧计划。"""
        cid = make_course(client)
        cleanup.append(cid)
        for i in range(8):
            client.post(
                "/api/flashcards",
                json={"course_id": cid, "front": f"Q{i}", "back": f"A{i}"},
            )
        exam = (dt.date.today() + dt.timedelta(days=5)).isoformat()
        p1 = client.post(
            "/api/review-plans/sprint",
            json={"course_id": cid, "exam_date": exam, "daily_budget_minutes": 20},
        ).json()
        p2 = client.post(
            "/api/review-plans/manual",
            json={"course_id": cid, "only_wrong": False, "daily_card_count": 5, "days": 2},
        ).json()
        active = client.get(f"/api/courses/{cid}/review-plans/active").json()
        assert active["id"] == p2["id"]
        assert active["id"] != p1["id"]


# ---------------------------------------------------------------------------
# 测验判分（不走 LLM：直接向库中塞题目测判分与统计）
# ---------------------------------------------------------------------------


class TestQuizGrading:
    def test_submit_and_stats(self, client, cleanup):
        cid = make_course(client)
        cleanup.append(cid)
        db = SessionLocal()
        try:
            quiz = Quiz(id=uuid.uuid4().hex, course_id=cid, question_count=2)
            db.add(quiz)
            db.flush()
            q1 = QuizQuestion(
                quiz_id=quiz.id, question_no=1, stem="题干一（足够长度）",
                options=["A", "B", "C", "D"], answer="A",
                explanation="解析一：内容足够长", difficulty="基础",
            )
            q2 = QuizQuestion(
                quiz_id=quiz.id, question_no=2, stem="题干二（足够长度）",
                options=["A", "B", "C", "D"], answer="B",
                explanation="解析二：内容足够长", difficulty="进阶",
            )
            db.add_all([q1, q2])
            db.commit()
            quiz_id, q1_id, q2_id = quiz.id, q1.id, q2.id
        finally:
            db.close()

        result = client.post(
            f"/api/quizzes/{quiz_id}/submit",
            json={"answers": [
                {"question_id": q1_id, "selected": "A"},
                {"question_id": q2_id, "selected": "C"},  # 答错
            ]},
        ).json()
        assert result["total"] == 2
        assert result["correct"] == 1
        assert 0.49 < result["accuracy"] < 0.51

        # 统计：正确率 50%
        stats = client.get(f"/api/courses/{cid}/stats").json()
        assert stats["total_attempts"] == 2
        assert 0.49 < stats["correct_rate"] < 0.51
        assert stats["total_cards"] == 0

    def test_health(self, client):
        assert client.get("/api/health").json()["ok"] is True
