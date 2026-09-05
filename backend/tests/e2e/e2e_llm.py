"""真实 LLM 全链路联调：双层问答（SSE 事件解析）→ 测验生成判分 → 讲解大纲。"""

import io
import json
import time

import httpx

BASE = "http://127.0.0.1:8000/api"

sample = """红黑树（Red-Black Tree）是一种自平衡二叉查找树。每个节点额外存储一个颜色位（红或黑）。

性质：
1. 节点是红色或黑色。
2. 根节点是黑色。
3. 所有叶子（NIL）是黑色。
4. 红色节点的两个子节点都是黑色（不存在连续红节点）。
5. 从任一节点到其每个叶子的路径包含相同数目的黑色节点（黑高相同）。

插入操作：新节点初始染红。若父节点为红则违反性质 4，需通过变色与旋转修复，共三种情况：
- 情况 1：叔节点为红——父与叔变黑、祖父变红，上移继续。
- 情况 2：叔为黑且新节点是"内侧"插入——先旋转成情况 3。
- 情况 3：叔为黑且为"外侧"插入——变色加单旋完成。

时间复杂度：插入、删除、查找均为 O(log n)。与 AVL 树相比红黑树旋转次数更少，插入删除更高效，被 C++ STL 的 map 与 Linux 内核采用。
"""

with httpx.Client(base_url=BASE, timeout=120) as c:
    # ---- 建课 + 上传 + 等索引 ----
    course = c.post("/courses", json={"name": "联调-数据结构"}).json()
    cid = course["id"]
    c.post(f"/courses/{cid}/documents", files={"file": ("rbtree.txt", io.BytesIO(sample.encode("utf-8")), "text/plain")})
    for _ in range(30):
        docs = c.get(f"/courses/{cid}/documents").json()
        if docs and docs[0]["status"] in ("indexed", "failed"):
            break
        time.sleep(2)
    print("[1] doc status:", docs[0]["status"], "chunks:", docs[0]["chunk_count"])
    assert docs[0]["status"] == "indexed"

    # ---- 双层问答（真实 LLM，SSE）----
    segments = []
    citations = None
    with c.stream("POST", "/chat/stream", json={"course_id": cid, "question": "红黑树插入新节点后如果违反了性质，怎么修复？"}, timeout=120) as r:
        assert r.status_code == 200, r.status_code
        cur_layer = None
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            evt = json.loads(line[5:])
            if evt["type"] == "segment_start":
                cur_layer = evt["layer"]
                segments.append({"layer": cur_layer, "text": ""})
            elif evt["type"] == "token":
                segments[-1]["text"] += evt["text"]
            elif evt["type"] == "citations":
                citations = evt["citations"]
            elif evt["type"] == "error":
                print("ERROR EVT:", evt["detail"])
                raise SystemExit(1)

    print("\n[2] 双层问答结果：")
    for s in segments:
        tag = "【资料】" if s["layer"] == "doc" else "【通识】"
        print(f"{tag} {s['text'][:180]}{'...' if len(s['text']) > 180 else ''}")
    doc_seg = next((s for s in segments if s["layer"] == "doc"), None)
    assert doc_seg and "变" in doc_seg["text"] or "旋" in doc_seg["text"], "doc 层应答出变色/旋转"
    assert citations and len(citations) > 0, "应有引用"
    print(f"    引用 {len(citations)} 条，首条：《{citations[0]['filename']}》{citations[0]['locator']}")

    # ---- 追问（多轮） ----
    with c.stream("POST", "/chat/stream", json={"course_id": cid, "session_id": None, "question": "它和 AVL 比有什么取舍？"}, timeout=120) as r:
        assert r.status_code == 200
        segs2 = []
        for line in r.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:])
                if evt["type"] == "segment_start":
                    segs2.append({"layer": evt["layer"], "text": ""})
                elif evt["type"] == "token":
                    segs2[-1]["text"] += evt["text"]
    print("\n[3] 追问（AVL 取舍）:")
    for s in segs2:
        tag = "【资料】" if s["layer"] == "doc" else "【通识】"
        print(f"{tag} {s['text'][:150]}")

    # ---- 测验生成（真实 LLM 出题） ----
    quiz = c.post("/quizzes", json={"course_id": cid, "count": 3}).json()
    print(f"\n[4] 测验生成：{quiz['question_count']} 题")
    for q in quiz["questions"]:
        print(f"    Q{q['question_no']}({q['difficulty']}): {q['stem'][:60]}...")
    assert quiz["question_count"] >= 1

    # 答第一题（选 A）提交
    first = quiz["questions"][0]
    result = c.post(f"/quizzes/{quiz['id']}/submit", json={"answers": [{"question_id": first["id"], "selected": "A"}]}).json()
    print(f"    提交 1 题: {result['correct']}/{result['total']} 对, 答案={result['items'][0]['answer']}")
    print(f"    解析: {result['items'][0]['explanation'][:100]}...")

    # ---- 错题转卡 ----
    wrong_q = first if result["items"][0]["is_correct"] is False else None
    if wrong_q is None:
        # 若答对了，构造错题：再答错一道
        if len(quiz["questions"]) > 1:
            second = quiz["questions"][1]
            r2 = c.post(f"/quizzes/{quiz['id']}/submit", json={"answers": [{"question_id": second["id"], "selected": "A"}]}).json()
            wrong_q = second if not r2["items"][0]["is_correct"] else None
    if wrong_q:
        card = c.post("/flashcards/from-quiz", json={"question_id": wrong_q["id"]}).json()
        print(f"\n[5] 错题转卡 OK: front={card['front'][:40]}... origin={card['origin']}")

    # ---- 讲解大纲 ----
    explain = c.post("/explain/outline", json={"course_id": cid, "topic": "平衡二叉树概览"}, timeout=120).json()
    print(f"\n[6] 讲解大纲：{len(explain['sections'])} 节")
    for sec in explain["sections"][:3]:
        linked = sum(len(n["linked_chunk_ids"]) for n in sec["nodes"])
        print(f"    {sec['title']}（{len(sec['nodes'])} 节点，挂接 {linked} 片段）")

    # ---- 统计 ----
    stats = c.get(f"/courses/{cid}/stats").json()
    print(f"\n[7] 统计: cards={stats['total_cards']} attempts={stats['total_attempts']} rate={stats['correct_rate']:.0%}")

    # 清理
    c.delete(f"/courses/{cid}")
    print("\n===== REAL LLM E2E ALL OK =====")
