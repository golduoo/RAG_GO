"""End-to-End RAG 流水线:query → retrieve → prompt → LLM → Answer。

CLI:
    uv run python -m src.generate.pipeline --query "顺丰特快多久到" --top-k 5
"""

from __future__ import annotations

import argparse
import sys

from src.generate.llm import LLMClient
from src.generate.prompts import build_rag_messages
from src.ingest.schema import Answer, RetrievedDoc
from src.logger import logger
from src.retrieval.base import Retriever
from src.retrieval.dense import DenseRetriever


DEFAULT_TOP_K = 5


class RagPipeline:
    """串联 Retriever + LLM 的最小闭环。"""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLMClient,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k

    def ask(self, query: str, top_k: int | None = None, stream: bool = False) -> Answer:
        k = top_k if top_k is not None else self.top_k
        if not query or not query.strip():
            return Answer(query=query, answer="(空 query)", citations=[])

        hits: list[RetrievedDoc] = self.retriever.search(query, top_k=k)
        if not hits:
            return Answer(
                query=query,
                answer="知识库中未找到相关信息",
                citations=[],
            )

        messages = build_rag_messages(query, [h.text for h in hits])
        if stream:
            chunks = []
            for tok in self.llm.stream(messages):
                chunks.append(tok)
                print(tok, end="", flush=True)
            print()
            answer_text = "".join(chunks)
        else:
            answer_text = self.llm.complete(messages)

        return Answer(query=query, answer=answer_text, citations=hits)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    p.add_argument("--no-stream", action="store_true")
    p.add_argument("--snippet", type=int, default=140)
    return p.parse_args()


def _print_answer(ans: Answer, snippet: int) -> None:
    print("=" * 70)
    print(f"Q: {ans.query}")
    print("-" * 70)
    print(f"A: {ans.answer}")
    if not ans.citations:
        print("\n(无引用来源)")
        return
    print("\n来源:")
    for i, c in enumerate(ans.citations, start=1):
        text = c.text.replace("\n", " ")[:snippet]
        doc = c.metadata.get("doc_id") if c.metadata else None
        print(f"  [{i}] score={c.score:.4f} doc={doc}\n      {text}")


def main() -> int:
    args = parse_args()
    retriever = DenseRetriever()
    llm = LLMClient()
    pipeline = RagPipeline(retriever=retriever, llm=llm, top_k=args.top_k)
    logger.info(f"query={args.query!r} top_k={args.top_k} stream={not args.no_stream}")

    if args.no_stream:
        ans = pipeline.ask(args.query, stream=False)
        _print_answer(ans, args.snippet)
    else:
        # 流式时 answer 边出边打印,最后再打印引用
        print("=" * 70)
        print(f"Q: {args.query}")
        print("-" * 70)
        print("A: ", end="", flush=True)
        ans = pipeline.ask(args.query, stream=True)
        # 流式时 ans.answer 已经在 stream 中打印过了,这里只补引用
        if ans.citations:
            print("\n来源:")
            for i, c in enumerate(ans.citations, start=1):
                text = c.text.replace("\n", " ")[: args.snippet]
                doc = c.metadata.get("doc_id") if c.metadata else None
                print(f"  [{i}] score={c.score:.4f} doc={doc}\n      {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
