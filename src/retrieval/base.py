"""检索器抽象基类。所有检索器(Dense / BM25 / Hybrid / Graph)实现 ``Retriever``。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.ingest.schema import RetrievedDoc


class Retriever(ABC):
    """单一职责:把 query 变成 top_k 个 ``RetrievedDoc``。"""

    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]:
        """返回按相关性降序的 top_k 条结果。空 query 应返回 []。"""

    def batch_search(self, queries: list[str], top_k: int = 10) -> list[list[RetrievedDoc]]:
        """默认逐条调 search;子类可以 override 做批量优化。"""
        return [self.search(q, top_k=top_k) for q in queries]
