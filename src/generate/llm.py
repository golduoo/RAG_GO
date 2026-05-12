"""LLM 调用封装(DeepSeek,OpenAI 兼容)。

- 流式 ``stream()``:逐 token yield(SSE 风格)
- 非流式 ``complete()``:一次性返回完整文本
- 失败自动重试:tenacity,最多 3 次,指数退避,**只重试 5xx 和限流**

CLI:
    uv run python -m src.generate.llm --prompt "你好,介绍一下顺丰特快"
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.logger import logger


def _is_retryable(exc: BaseException) -> bool:
    """只重试网络错误、限流、以及 5xx;4xx 立刻失败(避免无意义重试)。"""
    if isinstance(exc, (APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return 500 <= getattr(exc, "status_code", 0) < 600
    return False


_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


class LLMClient:
    """OpenAI 兼容客户端的薄封装。可注入 client 便于测试。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.model = model or settings.deepseek_model
        if client is not None:
            self._client = client
        else:
            key = api_key or settings.deepseek_api_key
            if not key:
                raise RuntimeError("DEEPSEEK_API_KEY 未配置,请在 .env 中填写")
            self._client = OpenAI(
                api_key=key,
                base_url=base_url or settings.deepseek_base_url,
            )

    @_RETRY
    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        """一次性返回完整文本。"""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    @_RETRY
    def stream(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Iterator[str]:
        """流式返回 token 增量。注意:整个 stream 调用作为单次重试单位。"""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt", required=True)
    p.add_argument("--no-stream", action="store_true")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--max-tokens", type=int, default=512)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    llm = LLMClient()
    logger.info(f"model={llm.model} stream={not args.no_stream}")
    messages = [{"role": "user", "content": args.prompt}]

    if args.no_stream:
        text = llm.complete(
            messages, temperature=args.temperature, max_tokens=args.max_tokens
        )
        print(text)
    else:
        for token in llm.stream(
            messages, temperature=args.temperature, max_tokens=args.max_tokens
        ):
            print(token, end="", flush=True)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
