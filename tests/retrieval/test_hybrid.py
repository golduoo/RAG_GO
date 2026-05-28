"""RRF 融合 + HybridRetriever 的单元测试。"""

from __future__ import annotations

import pytest

from src.ingest.schema import RetrievedDoc
from src.retrieval.base import Retriever
from src.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion


def _doc(doc_id: str, source: str = "dense", score: float = 0.0) -> RetrievedDoc:
    return RetrievedDoc(id=doc_id, text=f"text-{doc_id}", score=score, source=source)


def _ranking(ids: list[str], source: str = "dense") -> list[RetrievedDoc]:
    return [_doc(i, source) for i in ids]


class _FakeRetriever(Retriever):
    """返回预设 id 顺序的假检索器。"""

    def __init__(self, ids: list[str], source: str = "dense") -> None:
        self.ids = ids
        self.source = source

    def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]:
        return _ranking(self.ids[:top_k], self.source)


# ---------------------------------------------------------------------------
# reciprocal_rank_fusion
# ---------------------------------------------------------------------------


class TestRRF:
    def test_normal_multi_route(self):
        # A 在两路都靠前 → 应排第一
        r1 = _ranking(["A", "B", "C"])
        r2 = _ranking(["A", "C", "D"], source="bm25")
        out = reciprocal_rank_fusion([r1, r2], k=60, top_k=10)
        assert out[0].id == "A"
        assert {d.id for d in out} == {"A", "B", "C", "D"}
        assert all(d.source == "hybrid" for d in out)
        assert [d.rank for d in out] == list(range(len(out)))
        # 分数严格降序
        scores = [d.score for d in out]
        assert scores == sorted(scores, reverse=True)

    def test_single_ranking_preserves_order(self):
        r = _ranking(["X", "Y", "Z"])
        out = reciprocal_rank_fusion([r], k=60, top_k=10)
        assert [d.id for d in out] == ["X", "Y", "Z"]

    def test_empty_ranking_skipped(self):
        r1 = _ranking(["A", "B"])
        out = reciprocal_rank_fusion([r1, []], k=60, top_k=10)
        assert [d.id for d in out] == ["A", "B"]

    def test_all_empty_returns_empty(self):
        assert reciprocal_rank_fusion([[], []], k=60, top_k=10) == []

    def test_duplicate_doc_scores_accumulate(self):
        # 同一 doc 在两路同名次,分数应是单路的 2 倍
        r1 = _ranking(["A"])
        r2 = _ranking(["A"], source="bm25")
        single = reciprocal_rank_fusion([r1], k=60, top_k=10)
        double = reciprocal_rank_fusion([r1, r2], k=60, top_k=10)
        assert double[0].id == "A"
        assert double[0].score == pytest.approx(2 * single[0].score)

    def test_different_length_rankings(self):
        r1 = _ranking(["A", "B", "C", "D", "E"])
        r2 = _ranking(["C"], source="bm25")
        out = reciprocal_rank_fusion([r1, r2], k=60, top_k=10)
        # C 多一路加成,应超过原来排它前面的 B
        ids = [d.id for d in out]
        assert ids[0] == "C"
        assert set(ids) == {"A", "B", "C", "D", "E"}

    def test_top_k_truncates(self):
        r = _ranking(["A", "B", "C", "D"])
        out = reciprocal_rank_fusion([r], k=60, top_k=2)
        assert [d.id for d in out] == ["A", "B"]

    def test_invalid_k_raises(self):
        with pytest.raises(ValueError, match="k must be"):
            reciprocal_rank_fusion([_ranking(["A"])], k=0)


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------


class TestHybridRetriever:
    def test_fuses_two_routes(self):
        dense = _FakeRetriever(["A", "B", "C"], "dense")
        bm25 = _FakeRetriever(["A", "C", "D"], "bm25")
        hyb = HybridRetriever([dense, bm25], k=60)
        out = hyb.search("q", top_k=3)
        assert out[0].id == "A"
        assert len(out) == 3
        assert all(d.source == "hybrid" for d in out)

    def test_empty_query_returns_empty(self):
        hyb = HybridRetriever([_FakeRetriever(["A"])])
        assert hyb.search("", top_k=3) == []
        assert hyb.search("   ", top_k=3) == []

    def test_zero_topk_returns_empty(self):
        hyb = HybridRetriever([_FakeRetriever(["A"])])
        assert hyb.search("q", top_k=0) == []

    def test_empty_retrievers_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            HybridRetriever([])

    def test_invalid_k_raises(self):
        with pytest.raises(ValueError, match="k must be"):
            HybridRetriever([_FakeRetriever(["A"])], k=0)

    def test_single_route_equivalent_to_passthrough(self):
        hyb = HybridRetriever([_FakeRetriever(["X", "Y", "Z"])])
        out = hyb.search("q", top_k=3)
        assert [d.id for d in out] == ["X", "Y", "Z"]
