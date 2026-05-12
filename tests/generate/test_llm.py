"""LLMClient 单元测试,全程 mock OpenAI client。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIStatusError, RateLimitError

from src.generate.llm import LLMClient, _is_retryable
from src.generate.prompts import build_rag_messages, format_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completion(text: str):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_chunk(delta_text: str | None):
    delta = MagicMock()
    delta.content = delta_text
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _make_status_error(code: int) -> APIStatusError:
    req = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
    resp = httpx.Response(code, request=req)
    return APIStatusError(message=f"http {code}", response=resp, body=None)


@pytest.fixture
def mock_openai() -> MagicMock:
    c = MagicMock()
    c.chat.completions.create = MagicMock()
    return c


@pytest.fixture
def llm(mock_openai: MagicMock) -> LLMClient:
    return LLMClient(client=mock_openai, model="deepseek-chat-test")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_format_context_empty(self):
        assert format_context([]) == "(无)"

    def test_format_context_numbered(self):
        out = format_context(["A", "B"])
        assert "[1] A" in out and "[2] B" in out

    def test_build_rag_messages_shape(self):
        msgs = build_rag_messages("q", ["p1"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "q" in msgs[1]["content"]
        assert "[1] p1" in msgs[1]["content"]


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_retryable_5xx(self):
        assert _is_retryable(_make_status_error(500))
        assert _is_retryable(_make_status_error(503))

    def test_not_retryable_4xx(self):
        assert not _is_retryable(_make_status_error(400))
        assert not _is_retryable(_make_status_error(404))

    def test_retryable_rate_limit(self):
        req = httpx.Request("POST", "x")
        resp = httpx.Response(429, request=req)
        err = RateLimitError("too many", response=resp, body=None)
        assert _is_retryable(err)

    def test_not_retryable_generic(self):
        assert not _is_retryable(ValueError("nope"))


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


class TestComplete:
    def test_complete_normal(self, llm: LLMClient, mock_openai: MagicMock):
        mock_openai.chat.completions.create.return_value = _make_completion("hello")
        out = llm.complete([{"role": "user", "content": "hi"}])
        assert out == "hello"
        mock_openai.chat.completions.create.assert_called_once()
        _, kw = mock_openai.chat.completions.create.call_args
        assert kw["stream"] is False
        assert kw["model"] == "deepseek-chat-test"

    def test_complete_retry_on_5xx_then_success(
        self, llm: LLMClient, mock_openai: MagicMock
    ):
        mock_openai.chat.completions.create.side_effect = [
            _make_status_error(500),
            _make_status_error(503),
            _make_completion("ok"),
        ]
        # 让 retry 不要真等待
        with patch("src.generate.llm.wait_exponential", return_value=lambda *a, **k: 0):
            out = llm.complete([{"role": "user", "content": "hi"}])
        assert out == "ok"
        assert mock_openai.chat.completions.create.call_count == 3

    def test_complete_no_retry_on_4xx(self, llm: LLMClient, mock_openai: MagicMock):
        mock_openai.chat.completions.create.side_effect = _make_status_error(400)
        with pytest.raises(APIStatusError):
            llm.complete([{"role": "user", "content": "hi"}])
        assert mock_openai.chat.completions.create.call_count == 1

    def test_complete_give_up_after_3_tries(
        self, llm: LLMClient, mock_openai: MagicMock
    ):
        mock_openai.chat.completions.create.side_effect = _make_status_error(500)
        with pytest.raises(APIStatusError):
            llm.complete([{"role": "user", "content": "hi"}])
        assert mock_openai.chat.completions.create.call_count == 3


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


class TestStream:
    def test_stream_yields_tokens(self, llm: LLMClient, mock_openai: MagicMock):
        mock_openai.chat.completions.create.return_value = iter(
            [_make_chunk("Hel"), _make_chunk("lo"), _make_chunk(None), _make_chunk("!")]
        )
        out = list(llm.stream([{"role": "user", "content": "hi"}]))
        assert out == ["Hel", "lo", "!"]
        _, kw = mock_openai.chat.completions.create.call_args
        assert kw["stream"] is True
