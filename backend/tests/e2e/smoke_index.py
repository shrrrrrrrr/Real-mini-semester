"""端到端冒烟：上传真实文件 → 后台索引 → 检索命中。

验证完整数据流：解析 → 分块 → 嵌入（真实模型）→ BM25+向量+RRF 检索。
不依赖 LLM API（不测问答生成，该链路需用户 Key 后联调）。
"""

import sys
import time

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from app.db import init_db, SessionLocal
from app.main import create_app
from app.models import Chunk

# 构造一份"课程资料"：多主题文本，验证不同查询命中不同内容
SAMPLE = """红黑树是一种自平衡二叉查找树，插入和删除时通过旋转与变色保持平衡。

AVL 树是另一种平衡树，查询更快但插入旋转次数更多，适合读多写少场景。

图的最短路径算法包括 Dijkstra 算法与 Bellman-Ford 算法，后者支持负权边。

快速排序平均时间复杂度为 O(n log n)，最坏退化为 O(n^2)。

进程与线程的区别：进程拥有独立地址空间，线程共享所属进程的地址空间。
"""

init_db()
app = create_app()

with TestClient(app) as c:
    # 建课程 + 上传
    cid = c.post("/api/courses", json={"name": "冒烟课程"}).json()["id"]
    resp = c.post(
        f"/api/courses/{cid}/documents",
        files={"file": ("notes.txt", SAMPLE.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]

    # 轮询等待索引完成（含嵌入模型首次加载）
    deadline = time.time() + 180
    status = "pending"
    while time.time() < deadline:
        status = c.get(f"/api/courses/{cid}/documents").json()[0]["status"]
        if status in ("indexed", "failed", "rejected"):
            break
        time.sleep(2)
    print("final status:", status)
    assert status == "indexed", c.get(f"/api/courses/{cid}/documents").json()[0].get("fail_reason")

    # 检索冒烟：三个不同主题的查询应命中各自对应片段
    db = SessionLocal()
    try:
        from app.api.documents import select_indexed_chunks
        from app.core.retrieval import build_course_index

        chunks = select_indexed_chunks(db, cid)
        print(f"chunks: {len(chunks)}")
        index = build_course_index(chunks)
        for query, expect in [
            ("红黑树如何保持平衡", "红黑树"),
            ("负权边的最短路算法", "Bellman"),
            ("进程和线程有什么区别", "地址空间"),
        ]:
            hits = index.retrieve(query, top_k=2)
            contents = " ".join(h.content for h in hits)
            assert expect in contents, f"查询「{query}」未命中「{expect}」: {[h.locator for h in hits]}"
            print(f"  hit: {query} -> {expect} ✓ (top1: {hits[0].locator}, score={hits[0].score:.4f})")
    finally:
        db.close()

    # 清理
    c.delete(f"/api/courses/{cid}")
    print("SMOKE OK")
