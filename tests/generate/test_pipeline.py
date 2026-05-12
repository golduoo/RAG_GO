"""RagPipeline 单元测试,retriever 和 llm 全部 mock。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.generate.pipeline import RagPipeline
from src.ingest.schema import Answer, RetrievedDoc


@pytest.fixture
def fake_hits() -> list[RetrievedDoc]:
    return [
        RetrievedDoc(
            id=f"d-{i}",
            text=f"段落 {i}: 顺丰特快内容{i}",
            score=0.9 - 0.1 * i,
            source="dense",
            metadata={"doc_id": f"d{i}", "granularity": "paragraph"},
            rank=i,
        )
        for i in range(3)
    ]


@pytest.fixture
def mock_retriever(fake_hits) -> MagicMock:
    r = MagicMock()
    r.search = MagicMock(return_value=fake_hits)
    return r


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = MagicMock(return_value="顺丰特快通常 1-2 个工作日 [1][2]。")
    llm.stream = MagicMock(return_value=iter(["顺丰", "特快", "通常 1-2 个工作日。"]))
    return llm


@pytest.fixture
def pipeline(mock_retriever: MagicMock, mock_llm: MagicMock) -> RagPipeline:
    return RagPipeline(retriever=mock_retriever, llm=mock_llm, top_k=3)


class TestRagPipeline:
    def test_ask_normal(self, pipeline: RagPipeline, mock_retriever, mock_llm):
        ans = pipeline.ask("顺丰多久到")
        assert isinstance(ans, Answer)
        assert ans.query == "顺丰多久到"
        assert "顺丰特快" in ans.answer
        assert len(ans.citations) == 3
        mock_retriever.search.assert_called_once_with("顺丰多久到", top_k=3)
        mock_llm.complete.assert_called_once()
        # 验证 prompt 里塞进了 retrieved 段落
        _, kwargs = mock_llm.complete.call_args
        # complete(messages) — messages 是位置参数
        messages = mock_llm.complete.call_args[0][0]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "段落 0" in user_msg["content"]
        assert "[1]" in user_msg["content"]

    def test_ask_empty_query(self, pipeline: RagPipeline, mock_retriever):
        ans = pipeline.ask("")
        assert ans.citations == []
        assert "空" in ans.answer
        mock_retriever.search.assert_not_called()

    def test_ask_whitespace_query(self, pipeline: RagPipeline, mock_retriever):
        ans = pipeline.ask("   ")
        assert ans.citations == []
        mock_retriever.search.assert_not_called()

    def test_ask_no_hits(self, pipeline: RagPipeline, mock_retriever, mock_llm):
        mock_retriever.search.return_value = []
        ans = pipeline.ask("无关问题")
        assert ans.citations == []
        assert "未找到相关信息" in ans.answer
        mock_llm.complete.assert_not_called()  # 短路,不调 LLM

    def test_top_k_override(self, pipeline: RagPipeline, mock_retriever):
        pipeline.ask("q", top_k=10)
        mock_retriever.search.assert_called_once_with("q", top_k=10)

    def test_citations_preserve_order_and_score(self, pipeline: RagPipeline, fake_hits):
        ans = pipeline.ask("q")
        assert [c.id for c in ans.citations] == [h.id for h in fake_hits]
        assert [c.score for c in ans.citations] == [h.score for h in fake_hits]
