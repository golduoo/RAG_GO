"""混合检索:并行多路检索 + Reciprocal Rank Fusion(RRF)融合。

RRF 公式(每个文档):``score = Σ_routes 1 / (k + rank)``,rank 为 1-indexed 名次。
k 默认 60(Elastic / Azure AI Search 默认值):k 越大,名次差异被压得越平,
靠"多路都命中"取胜而非"单路排第一"。

CLI:
    uv run python -m src.retrieval.hybrid --query "顺丰特快多久到" --top-k 5
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from src.ingest.schema import RetrievedDoc
from src.logger import logger
from src.retrieval.base import Retriever

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[list[RetrievedDoc]],
    k: int = DEFAULT_RRF_K,
    top_k: int = 10,
) -> list[RetrievedDoc]:
    """把多路检索结果用 RRF 融合成一路。

    - 同一 doc(按 ``id``)在多路出现时,RRF 分数累加
    - 空路被自动跳过
    - 返回按融合分降序的前 ``top_k`` 条,``source="hybrid"``,``score`` 为 RRF 分,
      ``rank`` 重新从 0 编号

    Args:
        rankings: 多路结果,每路是按相关性降序的 RetrievedDoc 列表
        k: RRF 常数
        top_k: 返回条数
    """
    if k <= 0:
        raise ValueError(f"k must be > 0, got {k}")

    scores: dict[str, float] = {}
    docs: dict[str, RetrievedDoc] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc.id] = scores.get(doc.id, 0.0) + 1.0 / (k + rank)
            docs.setdefault(doc.id, doc)

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out: list[RetrievedDoc] = []
    for new_rank, (doc_id, score) in enumerate(ordered[: max(top_k, 0)]):
        base = docs[doc_id]
        out.append(
            base.model_copy(
                update={"score": score, "source": "hybrid", "rank": new_rank}
            )
        )
    return out


class HybridRetriever(Retriever):
    """并行调多路检索器,RRF 融合。各路只要实现 ``Retriever`` 即可热插拔。"""

    def __init__(self, retrievers: list[Retriever], k: int = DEFAULT_RRF_K) -> None:
        if not retrievers:
            raise ValueError("retrievers must not be empty")
        if k <= 0:
            raise ValueError(f"k must be > 0, got {k}")
        self.retrievers = retrievers
        self.k = k

    def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]:
        if not query or not query.strip():
            return []
        if top_k <= 0:
            return []

        # 各路多取一些候选(top_k 的 2 倍,至少 10),给 RRF 更多融合空间
        per_route_k = max(top_k * 2, 10)
        with ThreadPoolExecutor(max_workers=len(self.retrievers)) as pool:
            rankings = list(
                pool.map(lambda r: r.search(query, top_k=per_route_k), self.retrievers)
            )
        return reciprocal_rank_fusion(rankings, k=self.k, top_k=top_k)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--collection", default="chunks_v2")
    p.add_argument("--es-index", default="chunks_v2")
    p.add_argument("--k", type=int, default=DEFAULT_RRF_K, help="RRF 常数")
    p.add_argument("--snippet", type=int, default=120)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    from src.retrieval.dense import DenseRetriever
    from src.retrieval.sparse import BM25Retriever

    retriever = HybridRetriever(
        retrievers=[
            DenseRetriever(collection_name=args.collection),
            BM25Retriever(index_name=args.es_index),
        ],
        k=args.k,
    )
    logger.info(f"query: {args.query!r}  top_k={args.top_k}  rrf_k={args.k}")
    hits = retriever.search(args.query, top_k=args.top_k)
    if not hits:
        print("(no hits)")
        return 0
    for h in hits:
        snippet = h.text.replace("\n", " ")[: args.snippet]
        print(
            f"#{h.rank:02d}  rrf={h.score:.4f}  id={h.id[:24]}..  "
            f"doc={h.metadata.get('doc_id')}\n      {snippet}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
