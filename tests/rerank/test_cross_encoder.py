"""CrossEncoderReranker 单元测试,mock 模型不加载真权重。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.ingest.schema import RetrievedDoc
from src.rerank.cross_encoder import CrossEncoderReranker, RerankRetriever
from src.retrieval.base import Retriever


def _doc(doc_id: str, text: str, score: float = 0.0) -> RetrievedDoc:
    return RetrievedDoc(id=doc_id, text=text, score=score, source="hybrid")


@pytest.fixture
def fake_model() -> MagicMock:
    """伪 FlagReranker:compute_score 按 pairs 顺序返回预设分数。"""
    m = MagicMock()
    # 给第 2 个候选最高分,验证重排确实改变顺序
    m.compute_score = MagicMock(return_value=[0.1, 0.9, 0.4])
    return m


@pytest.fixture
def reranker(fake_model: MagicMock) -> CrossEncoderReranker:
    return CrossEncoderReranker(model=fake_model)


@pytest.fixture
def docs() -> list[RetrievedDoc]:
    return [
        _doc("d1-0", "顺丰标快航空次日达", 0.95),
        _doc("d2-0", "顺丰特惠陆运2-5天", 0.80),
        _doc("d3-0", "EMS 价格便宜", 0.70),
    ]


class TestRerank:
    def test_reorders_by_rerank_score(self, reranker, docs):
        out = reranker.rerank("特惠和标快区别", docs, top_n=3)
        # fake 给第 2 个候选(d2-0)最高分 → 应排第一
        assert out[0].id == "d2-0"
        assert [d.id for d in out] == ["d2-0", "d3-0", "d1-0"]
        assert all(d.source == "rerank" for d in out)
        assert [d.rank for d in out] == [0, 1, 2]
        assert out[0].score == pytest.approx(0.9)

    def test_top_n_truncates(self, reranker, docs):
        out = reranker.rerank("q", docs, top_n=1)
        assert len(out) == 1
        assert out[0].id == "d2-0"

    def test_empty_docs_returns_empty(self, reranker):
        assert reranker.rerank("q", [], top_n=3) == []

    def test_empty_query_returns_empty(self, reranker, docs):
        assert reranker.rerank("", docs, top_n=3) == []
        assert reranker.rerank("   ", docs, top_n=3) == []

    def test_zero_top_n_returns_empty(self, reranker, docs):
        assert reranker.rerank("q", docs, top_n=0) == []

    def test_preserves_metadata_and_doc_id(self, fake_model):
        fake_model.compute_score = MagicMock(return_value=[0.5])
        r = CrossEncoderReranker(model=fake_model)
        d = RetrievedDoc(
            id="d1-0",
            text="x",
            score=0.1,
            source="dense",
            metadata={"doc_id": "d1", "granularity": "paragraph"},
        )
        out = r.rerank("q", [d], top_n=1)
        assert out[0].metadata["doc_id"] == "d1"
        assert out[0].metadata["granularity"] == "paragraph"

    def test_score_scalar_normalized_to_list(self, fake_model):
        # 部分版本单条返回标量,score() 应统一成 list
        fake_model.compute_score = MagicMock(return_value=0.7)
        r = CrossEncoderReranker(model=fake_model)
        assert r.score("q", ["only one"]) == [0.7]

    def test_score_empty_passages(self, reranker):
        assert reranker.score("q", []) == []


class _FakeBase(Retriever):
    def __init__(self, docs: list[RetrievedDoc]) -> None:
        self.docs = docs
        self.last_top_k = None

    def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]:
        self.last_top_k = top_k
        return self.docs[:top_k]


class TestRerankRetriever:
    def test_recalls_candidates_then_reranks(self, reranker, docs):
        base = _FakeBase(docs)
        rr = RerankRetriever(base=base, reranker=reranker, candidate_k=50)
        out = rr.search("特惠和标快区别", top_k=2)
        # 基础检索器应被要求至少取 candidate_k 个候选
        assert base.last_top_k == 50
        # reranker 重排后(fake 给 d2-0 最高)d2-0 排第一,top_k=2 截断
        assert [d.id for d in out] == ["d2-0", "d3-0"]
        assert all(d.source == "rerank" for d in out)

    def test_empty_query_returns_empty(self, reranker, docs):
        rr = RerankRetriever(base=_FakeBase(docs), reranker=reranker)
        assert rr.search("", top_k=3) == []
