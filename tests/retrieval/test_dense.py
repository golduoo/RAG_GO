"""DenseRetriever 的单元测试,全程 mock,不连真 Milvus / 真 BGE-M3。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.ingest.schema import RetrievedDoc
from src.retrieval.dense import DenseRetriever


@pytest.fixture
def retriever(mock_embedder: MagicMock, mock_milvus_collection: MagicMock) -> DenseRetriever:
    return DenseRetriever(
        collection_name="chunks_v1_test",
        embedder=mock_embedder,
        collection=mock_milvus_collection,
    )


class TestDenseRetrieverSearch:
    def test_normal_returns_topk(self, retriever: DenseRetriever):
        out = retriever.search("顺丰多久到", top_k=3)
        assert len(out) == 3
        assert all(isinstance(d, RetrievedDoc) for d in out)
        # 按 score 降序(mock fixture 已经是降序)
        scores = [d.score for d in out]
        assert scores == sorted(scores, reverse=True)
        # source 标签正确
        assert all(d.source == "dense" for d in out)
        # rank 0-indexed
        assert [d.rank for d in out] == [0, 1, 2]

    def test_embedder_called_once(
        self,
        retriever: DenseRetriever,
        mock_embedder: MagicMock,
    ):
        retriever.search("query", top_k=3)
        mock_embedder.encode.assert_called_once()
        args, kwargs = mock_embedder.encode.call_args
        assert args[0] == ["query"]

    def test_milvus_search_called_with_topk(
        self,
        retriever: DenseRetriever,
        mock_milvus_collection: MagicMock,
    ):
        retriever.search("query", top_k=5)
        mock_milvus_collection.search.assert_called_once()
        _, kwargs = mock_milvus_collection.search.call_args
        assert kwargs["limit"] == 5
        assert kwargs["anns_field"] == "vector"

    def test_empty_query_returns_empty(self, retriever: DenseRetriever):
        assert retriever.search("", top_k=3) == []
        assert retriever.search("   ", top_k=3) == []

    def test_zero_topk_returns_empty(self, retriever: DenseRetriever):
        assert retriever.search("query", top_k=0) == []

    def test_metadata_flattened(self, retriever: DenseRetriever):
        out = retriever.search("query", top_k=1)
        md = out[0].metadata
        assert md["doc_id"] == "doc-1"
        assert md["granularity"] == "paragraph"
        assert md["corpus"] == "test"

    def test_batch_search(self, retriever: DenseRetriever, mock_milvus_collection: MagicMock):
        results = retriever.batch_search(["a", "b"], top_k=2)
        assert len(results) == 2
        assert all(len(r) == 3 for r in results)  # mock 总是返 3 条,top_k=2 没生效因为 mock 写死
        # mock 被调了 2 次(每条 query 一次)
        assert mock_milvus_collection.search.call_count == 2
