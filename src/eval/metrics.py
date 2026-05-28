"""检索质量指标:Recall@K, MRR, Hit@K。

约定:
- ``retrieved`` 是单次查询的检索结果(按相关性降序的 ID 列表)
- ``gold`` 是该查询的"正确"chunk ID 集合(EvalSample.gold_doc_ids)
- 所有指标在 [0, 1] 区间;指标 = NaN 不计入平均(此处用 0.0 占位)
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import mean


def hit_at_k(retrieved: Sequence[str], gold: Sequence[str], k: int) -> float:
    """top-K 命中(任一 gold 出现即 1,否则 0)。"""
    if not gold or k <= 0:
        return 0.0
    gold_set = set(gold)
    return 1.0 if any(r in gold_set for r in retrieved[:k]) else 0.0


def recall_at_k(retrieved: Sequence[str], gold: Sequence[str], k: int) -> float:
    """top-K 召回 = (top-K 中命中的不同 gold 数) / |gold|。

    用集合交集,避免 retrieved 中重复 id(如 doc 级口径下同文档多 chunk)被重复计数
    导致召回 > 1。
    """
    if not gold or k <= 0:
        return 0.0
    gold_set = set(gold)
    found = set(retrieved[:k]) & gold_set
    return len(found) / len(gold_set)


def reciprocal_rank(retrieved: Sequence[str], gold: Sequence[str]) -> float:
    """第一个 gold 出现位置的倒数;没出现返 0。位置 1-indexed。"""
    if not gold:
        return 0.0
    gold_set = set(gold)
    for rank, r in enumerate(retrieved, start=1):
        if r in gold_set:
            return 1.0 / rank
    return 0.0


def evaluate_batch(
    pairs: list[tuple[Sequence[str], Sequence[str]]],
    ks: tuple[int, ...] = (3, 5, 10),
) -> dict[str, float]:
    """批量计算并平均各项指标。返回 dict 便于序列化到 metrics.md。

    Args:
        pairs: [(retrieved_ids, gold_ids), ...] 每个查询一对
        ks: 计算 Recall@K / Hit@K 的 K 取值

    Returns:
        例:{"Recall@3": 0.78, "Recall@5": 0.85, "Hit@3": 0.83, "MRR": 0.72, ...}
    """
    if not pairs:
        return {}
    metrics: dict[str, float] = {}
    for k in ks:
        metrics[f"Recall@{k}"] = mean(recall_at_k(r, g, k) for r, g in pairs)
        metrics[f"Hit@{k}"] = mean(hit_at_k(r, g, k) for r, g in pairs)
    metrics["MRR"] = mean(reciprocal_rank(r, g) for r, g in pairs)
    return metrics
