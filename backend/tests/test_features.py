"""新增接口测试：profile 配置 / 任务轮询 / 分支树 / 重命名 / 仅资料过滤。"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import create_app
from app.models import ChatSession, Message, UserProfile


@pytest.fixture(scope="module")
def client():
    init_db()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_profile():
    """每用例前重置单行配置，避免相互污染。"""
    db = SessionLocal()
    try:
        p = db.get(UserProfile, 1)
        if p:
            p.nickname = "学习者"
            p.avatar = None
            p.llm_base_url = None
            p.llm_api_key = None
            p.llm_model = None
            db.commit()
    finally:
        db.close()
    yield


class TestProfile:
    def test_read_default(self, client):
        p = client.get("/api/profile").json()
        assert p["nickname"] == "学习者"
        assert p["llm_key_hint"] is None

    def test_update_nickname_and_key(self, client):
        r = client.patch(
            "/api/profile",
            json={"nickname": "小智", "llm_api_key": "sk-test123456789"},
        ).json()
        assert r["nickname"] == "小智"
        assert r["llm_key_hint"] == "sk-***6789"

    def test_key_never_returned_full(self, client):
        """安全：任何读取接口不返回完整 Key。"""
        client.patch("/api/profile", json={"llm_api_key": "sk-secretkey9999"})
        p = client.get("/api/profile").json()
        assert "sk-secretkey9999" not in str(p)
        assert p["llm_key_hint"].endswith("9999")

    def test_clear_key(self, client):
        client.patch("/api/profile", json={"llm_api_key": "sk-test123456789"})
        r = client.patch("/api/profile", json={"llm_api_key": "__clear__"}).json()
        assert r["llm_key_hint"] is None

    def test_avatar_size_guard(self, client):
        r = client.patch("/api/profile", json={"avatar": "x" * (250 * 1024)})
        assert r.status_code == 400


class TestBranchChat:
    def _make_course(self, client, name="树课程") -> str:
        return client.post("/api/courses", json={"name": name}).json()["id"]

    def test_tree_structure(self, client):
        """分支树：主干 Q1 → A1，从 A1 分岔 Q2a/Q2b，节点可重命名。"""
        cid = self._make_course(client)
        db = SessionLocal()
        try:
            # 幂等清理（前次失败可能遗留同名会话）
            old = db.get(ChatSession, "tree-test-1")
            if old:
                db.delete(old)
                db.commit()
            session = ChatSession(id="tree-test-1", course_id=cid, title="树测试")
            db.add(session)
            db.flush()
            # 主干
            q1 = Message(session_id=session.id, role="user", content="Q1 红黑树是什么")
            db.add(q1)
            db.flush()
            a1 = Message(
                session_id=session.id, role="assistant", content="A1 回答",
                parent_message_id=q1.id,
            )
            db.add(a1)
            db.flush()
            # 两个分支：都从 A1 追问
            q2a = Message(session_id=session.id, role="user", content="Q2a 旋转", parent_message_id=a1.id)
            db.add(q2a)
            db.flush()
            a2a = Message(session_id=session.id, role="assistant", content="A2a", parent_message_id=q2a.id)
            db.add(a2a)
            db.flush()
            q2b = Message(session_id=session.id, role="user", content="Q2b AVL", parent_message_id=a1.id)
            db.add(q2b)
            db.commit()
            sid = session.id
        finally:
            db.close()

        tree = client.get(f"/api/sessions/{sid}/tree").json()
        assert len(tree["roots"]) == 1  # 唯一主干根
        root = tree["roots"][0]
        assert root["content"].startswith("Q1")
        assert root["answer_id"] is not None
        assert len(root["children"]) == 2  # Q2a 与 Q2b 两个分支
        child_contents = {c["content"][:3] for c in root["children"]}
        assert child_contents == {"Q2a", "Q2b"}

        # 重命名分支
        q2a_id = next(c["id"] for c in root["children"] if c["content"].startswith("Q2a"))
        r = client.patch(f"/api/messages/{q2a_id}/rename", json={"branch_name": "旋转机制"}).json()
        assert r["branch_name"] == "旋转机制"

        # 树里可见新名
        tree2 = client.get(f"/api/sessions/{sid}/tree").json()
        named = next(
            c for c in tree2["roots"][0]["children"] if c["id"] == q2a_id
        )
        assert named["branch_name"] == "旋转机制"

        # 清理
        client.delete(f"/api/sessions/{sid}")

    def test_rename_validation(self, client):
        cid = self._make_course(client)
        db = SessionLocal()
        try:
            session = ChatSession(id="tree-test-2", course_id=cid, title="t2")
            db.add(session)
            db.flush()
            q = Message(session_id=session.id, role="user", content="Q")
            db.add(q)
            db.commit()
            sid, qid = session.id, q.id
        finally:
            db.close()
        assert client.patch(f"/api/messages/{qid}/rename", json={"branch_name": ""}).status_code == 400
        assert client.patch(f"/api/messages/{qid}/rename", json={"branch_name": "x" * 61}).status_code == 400
        client.delete(f"/api/sessions/{sid}")


class TestTasks:
    def test_task_not_found(self, client):
        assert client.get("/api/tasks/nonexistent").status_code == 404

    def test_task_lifecycle(self, client):
        """手动走 spawn/finish 验证任务状态机。"""
        from app.api.tasks import finish_task, spawn_task

        task_id = spawn_task("quiz", lambda tid: finish_task(tid, {"x": 1}))
        # 轮询至完成（线程毫秒级）
        import time

        for _ in range(50):
            t = client.get(f"/api/tasks/{task_id}").json()
            if t["status"] == "done":
                break
            time.sleep(0.1)
        assert t["status"] == "done"
        assert t["result"] == {"x": 1}


class TestQuizHistory:
    def test_list_and_detail(self, client):
        cid = client.post("/api/courses", json={"name": "历史测验课程"}).json()["id"]
        db = SessionLocal()
        try:
            from app.models import Quiz, QuizQuestion

            quiz = Quiz(id="hist-quiz-1", course_id=cid, question_count=1)
            db.add(quiz)
            db.flush()
            q = QuizQuestion(
                quiz_id=quiz.id, question_no=1, stem="历史题干（足长）",
                options=["A", "B", "C", "D"], answer="A",
                explanation="解析至少十个字以上", difficulty="基础",
            )
            db.add(q)
            db.commit()
            qid = q.id
        finally:
            db.close()

        # 未作答：列表 attempted=False；详情不带 answer
        assert client.get("/api/quizzes/hist-quiz-1").json()["attempted"] is False
        detail = client.get("/api/quizzes/hist-quiz-1").json()
        assert "answer" not in detail["questions"][0]

        # 提交后：attempted=True，详情带 answer 与 selected
        client.post(
            "/api/quizzes/hist-quiz-1/submit",
            json={"answers": [{"question_id": qid, "selected": "A"}]},
        )
        detail2 = client.get("/api/quizzes/hist-quiz-1").json()
        assert detail2["attempted"] is True
        assert detail2["questions"][0]["answer"] == "A"
        assert detail2["questions"][0]["selected"] == "A"
        assert detail2["questions"][0]["is_correct"] is True

        client.delete("/api/quizzes/hist-quiz-1")
        client.delete(f"/api/courses/{cid}")
