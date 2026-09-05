"""RAG 检索管线：BM25 关键词检索 + 向量语义检索 + RRF 融合。

设计（开发文档 §5.2 技术点①）：
- BM25 抓术语精确命中（低频专业词、符号）；
- 向量抓语义泛化（同义改写）；
- RRF 只依赖排名融合（两路分数量纲不同，直接加权不可行），
  实现仅十余行、天然去重（两路都命中者得分叠加）。

嵌入模型（MiniLM 384 维）本地运行；向量存 SQLite JSON 列，
检索时载入内存做 numpy 矩阵余弦——课程级规模下 < 50ms。
"""

import math
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from app.config import settings


@dataclass
class RetrievedChunk:
    """检索结果：含 chunk_id（DB 主键）与原文信息。"""

    chunk_id: int
    document_id: str
    filename: str
    locator: str
    content: str
    score: float


# ---------------------------------------------------------------------------
# 嵌入：懒加载单例（首次调用加载模型，约 90MB，之后常驻内存）
# ---------------------------------------------------------------------------

import threading

_embedder = None
_embedder_lock = threading.Lock()


def _get_embedder():
    """获取嵌入模型单例（线程安全）。

    关键工程决策：
    1. torch 模型在子线程中首次加载可能死锁（lazy module + 并发
       import 的已知问题）——全局双检锁保证只加载一次，且服务启动
       时在主线程预热（main.py → warmup_embedder）；
    2. 模型已缓存时设置 HF_HUB_OFFLINE，跳过 huggingface.co 的
       HEAD 联网检查——无代理环境下每个配置文件要重试 5 次约 2 分钟，
       这是 indexing 线程"假死"的第二原因。
    """
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:  # 双重检查
                import os

                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                from sentence_transformers import SentenceTransformer

                _embedder = SentenceTransformer(
                    settings.embedding_model, device="cpu"
                )
    return _embedder


def warmup_embedder() -> None:
    """服务启动时预加载模型（主线程完成，后台索引线程零死锁风险）。"""
    _get_embedder()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量计算嵌入（索引阶段用）。返回 384 维向量列表（JSON 可序列化）。"""
    model = _get_embedder()
    vecs = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def embed_query(query: str) -> np.ndarray:
    """查询嵌入（检索阶段用），已归一化。"""
    model = _get_embedder()
    return model.encode([query], normalize_embeddings=True)[0]


# ---------------------------------------------------------------------------
# 分词（BM25 用）：中英文混合的简易 bigram + 英文词元
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """中英文混合分词：英文按词、中文按 2 字符滑动窗口（bigram）。

    中文无空格，BM25 不切词会导致整页文本成一个"词元"，
    bigram 是无需词典的稳健做法。
    """
    tokens: list[str] = []
    current_ascii = []
    for ch in text:
        if ch.isascii() and (ch.isalnum()):
            current_ascii.append(ch.lower())
        else:
            if current_ascii:
                tokens.append("".join(current_ascii))
                current_ascii = []
            if "\u4e00" <= ch <= "\u9fff":  # 中文字符
                tokens.append(ch)
    if current_ascii:
        tokens.append("".join(current_ascii))
    # 中文 bigram
    bigrams = []
    for i in range(len(tokens) - 1):
        if len(tokens[i]) == 1 and len(tokens[i + 1]) == 1:
            bigrams.append(tokens[i] + tokens[i + 1])
    return tokens + bigrams


# ---------------------------------------------------------------------------
# RRF 融合
# ---------------------------------------------------------------------------


def rrf_fuse(rankings: list[list[int]], k: int | None = None) -> dict[int, float]:
    """倒数排名融合：合并多路排名为统一分数。

    k 为平滑常数（RRF 论文推荐 60）：避免某一路的第 1 名（1/(0+1)=1.0）
    完全碾压另一路的第 2 名；只在每路首次出现时累加（等价于排名聚合）。
    """
    if k is None:
        k = settings.rrf_k
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


# ---------------------------------------------------------------------------
# 检索主入口
# ---------------------------------------------------------------------------


class CourseIndex:
    """检索索引：一次构建、会话内复用。

    持有 BM25 语料与向量矩阵，供同一检索范围的多次查询复用
    （问答、测验、讲解挂接共享检索入口）。
    chunk 来源（owner 字段区分）：
    - doc：课程资料（filename 由调用方通过 doc_names 提供）；
    - book：书库图书（filename 由调用方通过 doc_names 提供书名）。
    """

    def __init__(self, chunks: list, doc_names: dict[str, str] | None = None):
        """chunks: ORM Chunk 列表；doc_names: document_id → 显示名（文件名/书名）。"""
        names = doc_names or {}
        entries = []
        for c in chunks:
            owner = getattr(c, "owner", "doc")
            entries.append(
                {
                    "chunk_id": c.id,
                    "document_id": c.document_id,
                    "filename": names.get(c.document_id, ""),
                    "locator": c.locator_value,
                    "content": c.content,
                }
            )
        self.entries = entries
        self._bm25: BM25Okapi | None = None
        self._matrix: np.ndarray | None = None
        if self.entries:
            corpus = [tokenize(e["content"]) for e in self.entries]
            self._bm25 = BM25Okapi(corpus)
            vecs = [c.embedding for c in chunks]
            if all(v is not None for v in vecs):
                # 行=chunk、列=维度；查询点积即余弦（向量已归一化）
                self._matrix = np.array(vecs, dtype=np.float32)

    def _bm25_ranking(self, query: str, n: int) -> list[int]:
        """BM25 路：返回按相关性降序的 chunk_id 列表（前 n）。"""
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = np.argsort(-scores)[:n]
        return [self.entries[i]["chunk_id"] for i in order if scores[i] > 0]

    def _vector_ranking(self, query: str, n: int) -> list[int]:
        """向量路：余弦相似度（点积，因已归一化）降序前 n。"""
        if self._matrix is None or self._matrix.size == 0:
            return []
        q = embed_query(query)
        sims = self._matrix @ q
        order = np.argsort(-sims)[:n]
        return [self.entries[i]["chunk_id"] for i in order if sims[i] > 0.01]

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """混合检索主入口：双路各取前 pool 名 → RRF 融合 → 前 top_k。"""
        if not self.entries:
            return []
        if top_k is None:
            top_k = settings.retrieval_top_k
        pool = settings.retrieval_pool
        rankings = [
            self._bm25_ranking(query, pool),
            self._vector_ranking(query, pool),
        ]
        fused = rrf_fuse(rankings)
        top = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
        by_id = {e["chunk_id"]: e for e in self.entries}
        return [
            RetrievedChunk(
                chunk_id=cid,
                document_id=by_id[cid]["document_id"],
                filename=by_id[cid]["filename"],
                locator=by_id[cid]["locator"],
                content=by_id[cid]["content"],
                score=score,
            )
            for cid, score in top
        ]


def build_course_index(db_chunks: list, doc_names: dict[str, str] | None = None) -> CourseIndex:
    """从 ORM Chunk 列表构建索引（供 API 层调用）。

    doc_names：document_id → 显示名（课程文件名或书库书名），
    调用方负责收集（检索层不感知 Document/Book 实体）。
    """
    return CourseIndex(db_chunks, doc_names=doc_names)
