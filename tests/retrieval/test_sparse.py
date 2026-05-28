"""BM25Retriever 的单元测试,全程 mock,不连真 ES。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.ingest.schema import RetrievedDoc
from src.retrieval.sparse import BM25Retriever


@pytest.fixture
def retriever(mock_es_client: MagicMock) -> BM25Retriever:
    return BM25Retriever(index_name="chunks_v2_test", client=mock_es_client)


class TestBM25RetrieverSearch:
    def test_normal_returns_topk(self, retriever: BM25Retriever):
        out = retriever.search("顺丰多久到", top_k=3)
        assert len(out) == 3
        assert all(isinstance(d, RetrievedDoc) for d in out)
        scores = [d.score for d in out]
        assert scores == sorted(scores, reverse=True)
        assert all(d.source == "bm25" for d in out)
        assert [d.rank for d in out] == [0, 1, 2]

    def test_es_search_called_with_topk_and_match(
        self, retriever: BM25Retriever, mock_es_client: MagicMock
    ):
        retriever.search("顺丰", top_k=5)
        mock_es_client.search.assert_called_once()
        _, kwargs = mock_es_client.search.call_args
        assert kwargs["size"] == 5
        assert kwargs["query"] == {"match": {"text": "顺丰"}}
        assert kwargs["index"] == "chunks_v2_test"

    def test_empty_query_returns_empty(self, retriever: BM25Retriever):
        assert retriever.search("", top_k=3) == []
        assert retriever.search("   ", top_k=3) == []
        # 空 query 不应打到 ES
        retriever.client.search.assert_not_called()

    def test_zero_topk_returns_empty(self, retriever: BM25Retriever):
        assert retriever.search("query", top_k=0) == []

    def test_metadata_carries_doc_id(self, retriever: BM25Retriever):
        out = retriever.search("query", top_k=1)
        md = out[0].metadata
        assert md["doc_id"] == "doc-1"
        assert md["granularity"] == "paragraph"
        assert md["corpus"] == "test"

    def test_no_hits_returns_empty(self, mock_es_client: MagicMock):
        mock_es_client.search = MagicMock(return_value={"hits": {"hits": []}})
        r = BM25Retriever(index_name="x", client=mock_es_client)
        assert r.search("query", top_k=3) == []

    def test_missing_index_raises(self):
        es = MagicMock()
        es.indices.exists = MagicMock(return_value=False)
        with pytest.raises(RuntimeError, match="not found"):
            BM25Retriever(index_name="nope", client=es)

    def test_batch_search(self, retriever: BM25Retriever, mock_es_client: MagicMock):
        results = retriever.batch_search(["a", "b"], top_k=2)
        assert len(results) == 2
        assert mock_es_client.search.call_count == 2
