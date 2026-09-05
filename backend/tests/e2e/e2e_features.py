"""新功能真实 LLM 验证：任务化生成（不中断）+ 分支对话 + 仅资料模式 + profile。"""

import io
import json
import time

import httpx

BASE = "http://127.0.0.1:8000/api"

sample = """红黑树是一种自平衡二叉查找树，通过变色与旋转保持平衡，操作复杂度 O(log n)。
"""

with httpx.Client(base_url=BASE, timeout=120) as c:
    # ---- profile：配置与脱敏 ----
    r = c.patch("/profile", json={"nickname": "小测", "llm_api_key": "sk-test-abcdef1234"}).json()
    assert r["llm_key_hint"] == "sk-***1234", r
    full = json.dumps(r)
    assert "sk-test-abcdef1234" not in full, "完整 Key 不得出现在读取响应"
    c.patch("/profile", json={"llm_api_key": "__clear__", "nickname": "学习者"})
    print("[1] profile 脱敏与清除 OK")

    # ---- 建课 + 上传 ----
    cid = c.post("/courses", json={"name": "新功能联调"}).json()["id"]
    c.post(f"/courses/{cid}/documents", files={"file": ("a.txt", io.BytesIO(sample.encode()), "text/plain")})
    for _ in range(30):
        docs = c.get(f"/courses/{cid}/documents").json()
        if docs and docs[0]["status"] in ("indexed", "failed"):
            break
        time.sleep(2)
    assert docs[0]["status"] == "indexed"
    print("[2] 上传索引 OK")

    # ---- 主干提问（真实 LLM）拿 assistant_id ----
    segs = []
    with c.stream("POST", "/chat/stream", json={"course_id": cid, "question": "红黑树怎么保持平衡？"}, timeout=120) as r:
        assert r.status_code == 200
        sid = None
        answer_id = None
        for line in r.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:])
                if evt["type"] == "session":
                    sid = evt["session_id"]
                elif evt["type"] == "done":
                    answer_id = evt["message_id"]
    assert answer_id, "应有 assistant 消息 id"
    print(f"[3] 主干提问 OK（session={sid[:8]}…, answer_id={answer_id}）")

    # ---- 分支追问：parent_message_id=answer_id → 新分支 ----
    with c.stream(
        "POST",
        "/chat/stream",
        json={"course_id": cid, "session_id": sid, "question": "和 AVL 比呢？", "parent_message_id": answer_id},
        timeout=120,
    ) as r:
        assert r.status_code == 200
        ok_branch = False
        for line in r.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:])
                if evt["type"] == "done":
                    ok_branch = True
    assert ok_branch
    print("[4] 分支追问 OK")

    # ---- 树结构 ----
    tree = c.get(f"/sessions/{sid}/tree").json()
    assert len(tree["roots"]) == 1, "一个主干根"
    root = tree["roots"][0]
    assert len(root["children"]) == 1, "主干下 1 个分支"
    branch_node = root["children"][0]
    # 重命名
    rn = c.patch(f"/messages/{branch_node['id']}/rename", json={"branch_name": "AVL对比"}).json()
    assert rn["branch_name"] == "AVL对比"
    tree2 = c.get(f"/sessions/{sid}/tree").json()
    assert tree2["roots"][0]["children"][0]["branch_name"] == "AVL对比"
    print("[5] 分支树 + 重命名 OK")

    # ---- 仅资料模式（资料里没有的内容应拒答）----
    segs_do = []
    with c.stream(
        "POST",
        "/chat/stream",
        json={"course_id": cid, "session_id": sid, "question": "量子计算的基本原理是什么？", "docs_only": True},
        timeout=120,
    ) as r:
        assert r.status_code == 200
        layer = None
        for line in r.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:])
                if evt["type"] == "segment_start":
                    layer = evt["layer"]
                    segs_do.append({"layer": layer, "text": ""})
                elif evt["type"] == "token":
                    segs_do[-1]["text"] += evt["text"]
    layers = {s["layer"] for s in segs_do}
    assert layers == {"doc"}, f"仅资料模式不应有 general 层: {layers}"
    print(f"[6] 仅资料模式 OK（层={layers}，回答={segs_do[0]['text'][:40]}…）")

    # ---- 任务化大纲（切页不中断验证：创建后立即查任务状态）----
    t = c.post("/explain/outline", json={"course_id": cid, "topic": "平衡树概览"}, timeout=30).json()
    task_id = t["task_id"]
    st = c.get(f"/tasks/{task_id}").json()
    print(f"[7] 大纲任务已创建（初始状态 {st['status']}）→ 轮询完成")
    for _ in range(60):
        st = c.get(f"/tasks/{task_id}").json()
        if st["status"] in ("done", "failed"):
            break
        time.sleep(2)
    assert st["status"] == "done", st.get("failed_reason")
    explain_id = st["result"]["id"]
    print(f"    大纲完成：{len(st['result']['sections'])} 节")

    # ---- 节点展开讲解 ----
    nt = c.post("/explain/node-expand", json={"explain_id": explain_id, "sec_index": 0, "node_index": 0}, timeout=30).json()
    for _ in range(60):
        st = c.get(f"/tasks/{nt['task_id']}").json()
        if st["status"] in ("done", "failed"):
            break
        time.sleep(2)
    assert st["status"] == "done", st.get("failed_reason")
    print(f"[8] 节点展开讲解 OK（{len(st['result']['content'])} 字）")

    # ---- 任务化测验 ----
    qt = c.post("/quizzes", json={"course_id": cid, "count": 3}, timeout=30).json()
    for _ in range(60):
        st = c.get(f"/tasks/{qt['task_id']}").json()
        if st["status"] in ("done", "failed"):
            break
        time.sleep(2)
    assert st["status"] == "done", st.get("failed_reason")
    quiz_id = st["result"]["id"]
    print(f"[9] 测验任务完成：{st['result']['question_count']} 题")

    # ---- 测验历史列表 + 详情（判分后带答案）----
    hist = c.get(f"/quizzes?course_id={cid}").json()
    assert any(h["id"] == quiz_id for h in hist)
    # 提交一题
    qid = st["result"]["questions"][0]["id"]
    c.post(f"/quizzes/{quiz_id}/submit", json={"answers": [{"question_id": qid, "selected": "A"}]})
    detail = c.get(f"/quizzes/{quiz_id}").json()
    assert detail["attempted"] is True
    assert detail["questions"][0].get("answer"), "判分后详情应带答案"
    print("[10] 测验历史 + 详情回看 OK")

    # 清理
    c.delete(f"/courses/{cid}")
    print("\n===== NEW FEATURES E2E ALL OK =====")
