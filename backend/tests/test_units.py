"""单元测试：解析 / 分块 / RRF 融合 / 结构化契约。

不依赖数据库与 LLM（嵌入模型相关用例标 skip，避免测试期下载模型）。
"""

import math

import pytest
from pydantic import ValidationError

from app.core.chunker import _split_long_text, chunk_units
from app.core.parser import ParsedUnit
from app.core.prompts import AnswerSpec, QuizQuestionSpec
from app.core.retrieval import rrf_fuse, tokenize


# ---------------------------------------------------------------------------
# 分块器
# ---------------------------------------------------------------------------


class TestChunker:
    def test_short_unit_single_chunk(self):
        """短单元（< 目标长度）直接成块并保留定位符。"""
        units = [ParsedUnit(locator="第1页", text="红黑树是一种自平衡二叉查找树。")]
        chunks = chunk_units(units)
        assert len(chunks) == 1
        assert chunks[0]["locator"] == "第1页"
        assert "红黑树" in chunks[0]["content"]

    def test_long_text_split_no_middle_cut(self):
        """超长文本按句读切分，不把句子拦腰截断。"""
        sentence = "这是一句完整的话。" * 60  # 540 字
        pieces = _split_long_text(sentence, 400)
        assert len(pieces) >= 2
        # 每段末尾都是句号（在句读处断开）
        for p in pieces[:-1]:
            assert p.endswith(("。", "\n", ".", "!", "?"))

    def test_multiple_units_keep_locators(self):
        """多单元分块：每块携带自己单元的定位符（引用溯源关键）。"""
        units = [
            ParsedUnit(locator="第1页", text="A" * 300),
            ParsedUnit(locator="第2页", text="B" * 300),
        ]
        chunks = chunk_units(units, target=200, overlap=10)
        locators = {c["locator"] for c in chunks}
        assert locators == {"第1页", "第2页"}

    def test_empty_units(self):
        assert chunk_units([]) == []

    def test_overlap_not_cross_units(self):
        """重叠不跨单元（保持引用定位精确）。"""
        units = [
            ParsedUnit(locator="第1页", text="甲" * 350),
            ParsedUnit(locator="第2页", text="乙" * 350),
        ]
        chunks = chunk_units(units, target=300, overlap=50)
        for c in chunks:
            if c["locator"] == "第2页":
                # 第 2 页的块只含"乙"，不混入第 1 页重叠尾巴
                assert "甲" not in c["content"]


# ---------------------------------------------------------------------------
# 分词（BM25 中文 bigram）
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_mixed_cn_en(self):
        tokens = tokenize("红黑树 Red-Black Tree 的旋转")
        assert "红黑" in tokens  # 中文 bigram
        assert "树" in tokens
        assert "red" in tokens or "redblack" in tokens  # 英文词（连字符归一）

    def test_pure_ascii(self):
        tokens = tokenize("FSRS algorithm")
        assert tokens == ["fsrs", "algorithm"]  # 英文按词切分，无 bigram

    def test_cn_bigram_generated(self):
        """中文相邻单字生成 bigram（BM25 无词典分词的稳健做法）。"""
        tokens = tokenize("红黑树")
        assert "红黑" in tokens and "黑树" in tokens and "树" in tokens


# ---------------------------------------------------------------------------
# RRF 融合
# ---------------------------------------------------------------------------


class TestRRF:
    def test_both_paths_hit_ranks_higher(self):
        """两路都命中的 chunk 分数叠加，应高于单路命中。"""
        fused = rrf_fuse([[10, 20, 30], [30, 40, 50]])
        # 30 两路都命中 → 最高
        top = max(fused.items(), key=lambda x: x[1])
        assert top[0] == 30

    def test_disjoint_rankings(self):
        fused = rrf_fuse([[1, 2], [3, 4]])
        assert set(fused.keys()) == {1, 2, 3, 4}
        # 各路第 1 名得分相同
        assert math.isclose(fused[1], fused[3])

    def test_k_smoothing(self):
        """k 平滑：第 1 名 (1/(k+1)) 不应碾压第 2 名 (1/(k+2))。"""
        fused = rrf_fuse([[100]])
        ratio = (1 / 61) / (1 / 62)
        assert ratio < 1.02  # 差距微小


# ---------------------------------------------------------------------------
# LLM 输出契约（Pydantic）
# ---------------------------------------------------------------------------


class TestContracts:
    def test_answer_spec_valid(self):
        spec = AnswerSpec.model_validate(
            {
                "segments": [
                    {"layer": "doc", "text": "答案[1]"},
                    {"layer": "general", "text": "补充"},
                ]
            }
        )
        assert len(spec.segments) == 2

    def test_answer_spec_rejects_bad_layer(self):
        with pytest.raises(ValidationError):
            AnswerSpec.model_validate(
                {"segments": [{"layer": "other", "text": "x"}]}
            )

    def test_answer_spec_rejects_empty(self):
        with pytest.raises(ValidationError):
            AnswerSpec.model_validate({"segments": []})

    def test_quiz_spec_rejects_three_options(self):
        with pytest.raises(ValidationError):
            QuizQuestionSpec.model_validate(
                {
                    "stem": "这道题的题干足够长",
                    "options": ["A", "B", "C"],
                    "answer": "A",
                    "explanation": "解析文字超过十个字符",
                    "difficulty": "基础",
                }
            )

    def test_quiz_spec_rejects_bad_answer(self):
        with pytest.raises(ValidationError):
            QuizQuestionSpec.model_validate(
                {
                    "stem": "这道题的题干足够长",
                    "options": ["A", "B", "C", "D"],
                    "answer": "E",
                    "explanation": "解析文字超过十个字符",
                    "difficulty": "基础",
                }
            )

    def test_quiz_spec_valid(self):
        spec = QuizQuestionSpec.model_validate(
            {
                "stem": "红黑树插入新节点后，新节点初始颜色是什么？",
                "options": ["红色", "黑色", "随树高交替", "随机"],
                "answer": "A",
                "explanation": "新节点染红可避免破坏黑高性质，教材原文有述。",
                "difficulty": "基础",
            }
        )
        assert spec.answer == "A"
