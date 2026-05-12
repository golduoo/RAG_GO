"""Dense 检索:BGE-M3 编码 query → Milvus HNSW 近邻搜索。

CLI:
    uv run python -m src.retrieval.dense --query "顺丰特快多久到" --top-k 5
"""

from __future__ import annotations

import argparse
import sys

from pymilvus import Collection, connections, utility

from src.config import settings
from src.ingest.indexer import BGEEmbedder
from src.ingest.schema import RetrievedDoc
from src.logger import logger
from src.retrieval.base import Retriever


DEFAULT_OUTPUT_FIELDS = ("id", "doc_id", "text", "granularity", "metadata")
DEFAULT_SEARCH_PARAMS = {"metric_type": "COSINE", "params": {"ef": 64}}


class DenseRetriever(Retriever):
    """BGE-M3 + Milvus HNSW 检索。

    依赖注入设计:``embedder`` 和 ``collection`` 可被 mock,便于单元测试。
    """

    def __init__(
        self,
        collection_name: str = settings.milvus_collection,
        embedder: BGEEmbedder | None = None,
        collection: Collection | None = None,
        host: str = settings.milvus_host,
        port: str = settings.milvus_port,
        search_params: dict | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedder = embedder or BGEEmbedder()
        self.search_params = search_params or DEFAULT_SEARCH_PARAMS
        if collection is not None:
            self.collection = collection
        else:
            connections.connect(alias="default", host=host, port=port)
            if not utility.has_collection(collection_name):
                raise RuntimeError(
                    f"Milvus collection '{collection_name}' not found. "
                    "请先跑 scripts/ingest.py。"
                )
            self.collection = Collection(collection_name)
            self.collection.load()

    def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]:
        if not query or not query.strip():
            return []
        if top_k <= 0:
            return []

        vec = self.embedder.encode([query])[0]
        results = self.collection.search(
            data=[vec],
            anns_field="vector",
            param=self.search_params,
            limit=top_k,
            output_fields=list(DEFAULT_OUTPUT_FIELDS),
        )

        hits = results[0] if results else []
        out: list[RetrievedDoc] = []
        for rank, hit in enumerate(hits):
            entity = hit.entity if hasattr(hit, "entity") else hit
            out.append(
                RetrievedDoc(
                    id=str(_get(entity, "id")),
                    text=str(_get(entity, "text")),
                    score=float(hit.score) if hasattr(hit, "score") else 0.0,
                    source="dense",
                    metadata={
                        "doc_id": _get(entity, "doc_id"),
                        "granularity": _get(entity, "granularity"),
                        **(_get(entity, "metadata") or {}),
                    },
                    rank=rank,
                )
            )
        return out


def _get(entity: object, key: str) -> object:
    """Milvus SDK 不同版本/不同 mock 下 entity 取值方式不同,统一兜底。"""
    if isinstance(entity, dict):
        return entity.get(key)
    if hasattr(entity, "get"):
        try:
            return entity.get(key)
        except Exception:  # noqa: BLE001
            pass
    return getattr(entity, key, None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--collection", default=settings.milvus_collection)
    p.add_argument("--snippet", type=int, default=120, help="结果片段最多打印多少字符")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    retriever = DenseRetriever(collection_name=args.collection)
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
