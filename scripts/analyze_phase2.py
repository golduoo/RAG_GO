"""Phase 2 诊断分析(一次性):为什么 Hybrid 在抗泄漏集上没超过 Dense。

跑一次 Dense / BM25(缓存每条 query 的文档排名),离线算:
1. Dense top-3 命中但 Hybrid top-3 漏掉的 case 明细
2. 加权 RRF ablation(扫 dense:bm25 权重)
3. 分 query_type 的 Recall@3 / MRR

用法:
    uv run python scripts/analyze_phase2.py --eval data/eval/eval_v1_paraphrased.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from src.eval.metrics import reciprocal_rank, recall_at_k
from src.eval.schema import EvalSample
from src.retrieval.dense import DenseRetriever
from src.retrieval.sparse import BM25Retriever

DEPTH = 50
RRF_K = 60


def load(path: Path) -> list[EvalSample]:
    return [EvalSample(**json.loads(line)) for line in path.open(encoding="utf-8")]


def to_docs(hits) -> list[str]:
    """chunk 排名 → 去重的文档排名(保留首次出现名次)。"""
    out, seen = [], set()
    for h in hits:
        d = str(h.metadata.get("doc_id"))
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def weighted_rrf(dense_docs, bm25_docs, wd, wb, k=RRF_K) -> list[str]:
    score: dict[str, float] = defaultdict(float)
    for docs, w in ((dense_docs, wd), (bm25_docs, wb)):
        if w == 0:
            continue
        for rank, d in enumerate(docs, start=1):
            score[d] += w / (k + rank)
    return [d for d, _ in sorted(score.items(), key=lambda kv: kv[1], reverse=True)]


def gold_of(s: EvalSample) -> str:
    return str(s.metadata.get("src_doc_id") or s.gold_doc_ids[0].rsplit("-", 1)[0])


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eval", type=Path, default=Path("data/eval/eval_v1_paraphrased.jsonl"))
    ap.add_argument("--collection", default="chunks_v2")
    ap.add_argument("--es-index", default="chunks_v2")
    args = ap.parse_args()

    samples = load(args.eval)
    dense = DenseRetriever(collection_name=args.collection)
    bm25 = BM25Retriever(index_name=args.es_index)

    rows = []  # (sample, gold, dense_docs, bm25_docs)
    for s in samples:
        d_docs = to_docs(dense.search(s.question, top_k=DEPTH))
        b_docs = to_docs(bm25.search(s.question, top_k=DEPTH))
        rows.append((s, gold_of(s), d_docs, b_docs))

    # ---------- 2. 加权 RRF ablation ----------
    print("\n===== 2. Weighted RRF ablation (paraphrased, doc-level) =====")
    print(f"{'dense:bm25':>12} | {'Recall@3':>9} | {'MRR':>7}")
    weights = [(1, 0), (0, 1), (1, 1), (2, 1), (3, 1), (5, 1), (10, 1)]
    for wd, wb in weights:
        r3, mrr = [], []
        for _, gold, dd, bb in rows:
            fused = weighted_rrf(dd, bb, wd, wb)
            r3.append(recall_at_k(fused, [gold], 3))
            mrr.append(reciprocal_rank(fused, [gold]))
        tag = f"{wd}:{wb}"
        print(f"{tag:>12} | {mean(r3):>9.4f} | {mean(mrr):>7.4f}")

    # ---------- 3. 分 query_type ----------
    print("\n===== 3. By question_type (paraphrased, doc-level) =====")
    by_type: dict[str, list] = defaultdict(list)
    for r in rows:
        by_type[r[0].question_type].append(r)
    print(f"{'type':>12} | {'n':>3} | {'dense R@3':>9} | {'bm25 R@3':>9} | {'hyb R@3':>8} | {'hyb MRR':>8}")
    for qtype, group in by_type.items():
        d3 = mean([recall_at_k(dd, [g], 3) for _, g, dd, _ in group])
        b3 = mean([recall_at_k(bb, [g], 3) for _, g, _, bb in group])
        h3 = mean([recall_at_k(weighted_rrf(dd, bb, 1, 1), [g], 3) for _, g, dd, bb in group])
        hm = mean([reciprocal_rank(weighted_rrf(dd, bb, 1, 1), [g]) for _, g, dd, bb in group])
        print(f"{qtype:>12} | {len(group):>3} | {d3:>9.4f} | {b3:>9.4f} | {h3:>8.4f} | {hm:>8.4f}")

    # ---------- 1. Dense 命中 / Hybrid(1:1) 漏 的 case ----------
    print("\n===== 1. Dense top-3 HIT but Hybrid(1:1) top-3 MISS =====")
    n = 0
    for s, gold, dd, bb in rows:
        hyb = weighted_rrf(dd, bb, 1, 1)
        dense_hit = gold in dd[:3]
        hyb_hit = gold in hyb[:3]
        if dense_hit and not hyb_hit:
            n += 1
            bm25_rank = bb.index(gold) + 1 if gold in bb else None
            dense_rank = dd.index(gold) + 1 if gold in dd else None
            print(f"\n[{n}] qid={s.qid}  type={s.question_type}")
            print(f"    Q: {s.question}")
            print(f"    gold doc: {gold}")
            print(f"    dense rank of gold = {dense_rank}  |  bm25 rank of gold = {bm25_rank}")
            print(f"    hybrid top-3 docs = {hyb[:3]}")
    print(f"\n总计 Dense命中但Hybrid漏 的样本数: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
