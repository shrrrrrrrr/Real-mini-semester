"""书库 + 新 UI 功能真实 E2E：上传图书 → 勾选并入检索 → 回答引用书名。"""

import io
import json
import time

import httpx

BASE = "http://127.0.0.1:8000/api"

# 模拟一本"教材"：内容独立于课程资料
BOOK_TEXT = """图（Graph）是由顶点集合和边集合组成的离散结构。

图的遍历算法包括深度优先搜索（DFS）与广度优先搜索（BFS）。DFS 沿一条路径走到底再回溯，BFS 按层次逐圈扩展。

Dijkstra 算法解决非负权图的单源最短路径问题，时间复杂度 O((V+E)logV)。

拓扑排序用于有向无环图（DAG），典型应用是课程先修关系与构建依赖。
"""

COURSE_TEXT = """红黑树是一种自平衡二叉查找树，通过变色与旋转保持平衡。
"""

with httpx.Client(base_url=BASE, timeout=120) as c:
    # ---- 上传书 ----
    r = c.post(
        "/books",
        files={"file": ("graph-textbook.txt", io.BytesIO(BOOK_TEXT.encode("utf-8")), "text/plain")},
        data={"title": "图论教材"},
    )
    assert r.status_code == 201, r.text
    book = r.json()
    print("[1] 上传图书 OK：", book["title"], "封面前缀:", book["cover"][:26])
    assert book["cover"].startswith("data:image/png;base64,")

    for _ in range(30):
        books = c.get("/books").json()
        b = next((x for x in books if x["id"] == book["id"]), None)
        if b and b["status"] in ("indexed", "failed", "rejected"):
            break
        time.sleep(2)
    assert b["status"] == "indexed", b.get("fail_reason")
    print(f"[2] 图书索引 OK：{b['chunk_count']} 块")

    # ---- 建课 + 课程资料（内容与书完全不同） ----
    course = c.post("/courses", json={"name": "书库联调课"}).json()
    cid = course["id"]
    c.post(f"/courses/{cid}/documents", files={"file": ("rb.txt", io.BytesIO(COURSE_TEXT.encode()), "text/plain")})
    for _ in range(30):
        docs = c.get(f"/courses/{cid}/documents").json()
        if docs and docs[0]["status"] in ("indexed", "failed"):
            break
        time.sleep(2)
    assert docs[0]["status"] == "indexed"

    # ---- 不勾书提问（图论问题）：资料里没有，应拒答或仅通识 ----
    segs = []
    with c.stream(
        "POST",
        "/chat/stream",
        json={"course_id": cid, "question": "Dijkstra 算法的时间复杂度是多少？", "docs_only": True, "book_ids": []},
        timeout=120,
    ) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:])
                if evt["type"] == "segment_start":
                    segs.append({"layer": evt["layer"], "text": ""})
                elif evt["type"] == "token":
                    segs[-1]["text"] += evt["text"]
    no_book_text = " ".join(s["text"] for s in segs)
    assert "资料中未找到" in no_book_text, f"不勾书时应拒答：{no_book_text[:80]}"
    print("[3] 不勾书：资料外问题正确拒答 OK")

    # ---- 勾书提问：应从书里检索出 Dijkstra ----
    segs2 = []
    citations = []
    with c.stream(
        "POST",
        "/chat/stream",
        json={
            "course_id": cid,
            "question": "Dijkstra 算法的时间复杂度是多少？",
            "docs_only": True,
            "book_ids": [book["id"]],
        },
        timeout=120,
    ) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:])
                if evt["type"] == "segment_start":
                    segs2.append({"layer": evt["layer"], "text": ""})
                elif evt["type"] == "token":
                    segs2[-1]["text"] += evt["text"]
                elif evt["type"] == "citations":
                    citations = evt["citations"]
    text2 = " ".join(s["text"] for s in segs2)
    assert "log" in text2 or "O(" in text2, f"应答出复杂度：{text2[:80]}"
    book_cited = [ct for ct in citations if ct["filename"] == "图论教材"]
    assert book_cited, f"引用应含书名《图论教材》: {[ct['filename'] for ct in citations]}"
    print(f"[4] 勾书检索命中 OK（引用《图论教材》×{len(book_cited)}）")

    # ---- 删除书：级联清块 ----
    c.delete(f"/books/{book['id']}")
    books = c.get("/books").json()
    assert not any(x["id"] == book["id"] for x in books)
    print("[5] 删除图书 OK")

    c.delete(f"/courses/{cid}")
    print("\n===== BOOKS E2E ALL OK =====")
