"""BM25 稀疏检索:Elasticsearch ``match`` 查询(分词用 ik_smart,见 ADR-005)。

接口与 ``DenseRetriever`` 完全一致,可热插拔(同实现 ``Retriever``)。

CLI:
    uv run python -m src.retrieval.sparse --query "顺丰特快多久到" --top-k 5
"""

from __future__ import annotations

import argparse
import sys

from elasticsearch import Elasticsearch

from src.config import settings
from src.ingest.schema import RetrievedDoc
from src.logger import logger
from src.retrieval.base import Retriever


class BM25Retriever(Retriever):
    """ES BM25 检索。

    依赖注入设计:``client`` 可被 mock,便于单元测试。
    """

    def __init__(
        self,
        index_name: str = settings.es_index,
        client: Elasticsearch | None = None,
        host: str = settings.es_host,
        text_field: str = "text",
    ) -> None:
        self.index_name = index_name
        self.text_field = text_field
        self.client = client or Elasticsearch(host, request_timeout=30)
        if not self.client.indices.exists(index=index_name):
            raise RuntimeError(
                f"ES index '{index_name}' not found. 请先跑 scripts/ingest.py。"
            )

    def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]:
        if not query or not query.strip():
            return []
        if top_k <= 0:
            return []

        res = self.client.search(
            index=self.index_name,
            query={"match": {self.text_field: query}},
            size=top_k,
        )
        hits = res.get("hits", {}).get("hits", [])
        out: list[RetrievedDoc] = []
        for rank, hit in enumerate(hits):
            src = hit.get("_source", {})
            md = dict(src.get("metadata") or {})
            md["doc_id"] = src.get("doc_id")
            md["granularity"] = src.get("granularity")
            out.append(
                RetrievedDoc(
                    id=str(hit.get("_id")),
                    text=str(src.get("text", "")),
                    score=float(hit.get("_score") or 0.0),
                    source="bm25",
                    metadata=md,
                    rank=rank,
                )
            )
        return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--index", default=settings.es_index)
    p.add_argument("--snippet", type=int, default=120, help="结果片段最多打印多少字符")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    retriever = BM25Retriever(index_name=args.index)
    logger.info(f"query: {args.query!r}  top_k={args.top_k}")
    hits = retriever.search(args.query, top_k=args.top_k)

    if not hits:
        print("(no hits)")
        return 0

    for h in hits:
        snippet = h.text.replace("\n", " ")[: args.snippet]
        print(
            f"#{h.rank:02d}  score={h.score:.4f}  id={h.id[:24]}..  "
            f"doc={h.metadata.get('doc_id')}\n"
            f"      {snippet}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
