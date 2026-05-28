"""跑评估:对每条 EvalSample 调 DenseRetriever,算 Recall/MRR,追加写 metrics.md。

用法:
    uv run python scripts/run_eval.py --phase 1
    uv run python scripts/run_eval.py --phase 1 --eval data/eval/eval_v1.jsonl --collection chunks_v1 --top-k 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tqdm import tqdm

from src.config import settings
from src.eval.metrics import evaluate_batch
from src.eval.metrics_logger import append_phase_report
from src.eval.schema import EvalSample
from src.ingest.schema import RetrievedDoc
from src.logger import logger
from src.retrieval.base import Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.sparse import BM25Retriever


DEFAULT_EVAL = Path("data/eval/eval_v1.jsonl")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", type=int, required=True)
    p.add_argument("--title", default="Dense Baseline", help="metrics.md 中的报告标题")
    p.add_argument("--eval", type=Path, default=DEFAULT_EVAL)
    p.add_argument("--collection", default=settings.milvus_collection)
    p.add_argument("--es-index", default=settings.es_index)
    p.add_argument(
        "--retriever",
        choices=("dense", "bm25", "hybrid"),
        default="dense",
        help="dense=Milvus / bm25=ES / hybrid=RRF 融合",
    )
    p.add_argument(
        "--match-level",
        choices=("chunk", "doc"),
        default="doc",
        help="doc=命中算到原文档(可比不同切分),chunk=精确 chunk id(Phase1 旧口径)",
    )
    p.add_argument("--rrf-k", type=int, default=60)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--ks", type=int, nargs="+", default=[3, 5, 10])
    p.add_argument("--notes", default="")
    return p.parse_args()


def load_eval(path: Path) -> list[EvalSample]:
    samples: list[EvalSample] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            samples.append(EvalSample(**json.loads(line)))
    return samples


def build_retriever(args: argparse.Namespace) -> tuple[Retriever, str]:
    if args.retriever == "dense":
        r = DenseRetriever(collection_name=args.collection)
        desc = "DenseRetriever(BGE-M3 + Milvus HNSW M=16 efC=200, ef=64)"
    elif args.retriever == "bm25":
        r = BM25Retriever(index_name=args.es_index)
        desc = "BM25Retriever(ES ik_smart)"
    else:
        r = HybridRetriever(
            retrievers=[
                DenseRetriever(collection_name=args.collection),
                BM25Retriever(index_name=args.es_index),
            ],
            k=args.rrf_k,
        )
        desc = f"HybridRetriever(Dense + BM25, RRF k={args.rrf_k})"
    return r, desc


def _src_doc_id(sample: EvalSample) -> str:
    """gold 文档 id:优先 metadata.src_doc_id,否则从 gold chunk id 推回。"""
    sid = sample.metadata.get("src_doc_id")
    if sid:
        return str(sid)
    return sample.gold_doc_ids[0].rsplit("-", 1)[0]


def build_pairs(
    hits: list[RetrievedDoc], sample: EvalSample, match_level: str
) -> tuple[list[str], list[str]]:
    if match_level == "doc":
        # 按文档去重,保留首次出现的名次:把 chunk 排名折叠成文档排名,
        # 让多粒度(同文档多 chunk)与单粒度在 doc 空间公平对比。
        retrieved: list[str] = []
        seen: set[str] = set()
        for h in hits:
            d = str(h.metadata.get("doc_id"))
            if d not in seen:
                seen.add(d)
                retrieved.append(d)
        gold = [_src_doc_id(sample)]
    else:
        retrieved = [h.id for h in hits]
        gold = sample.gold_doc_ids
    return retrieved, gold


def main() -> int:
    args = parse_args()

    samples = load_eval(args.eval)
    logger.info(
        f"loaded {len(samples)} eval samples from {args.eval} "
        f"| retriever={args.retriever} match_level={args.match_level}"
    )

    retriever, retriever_desc = build_retriever(args)

    # doc 级口径要按文档去重,检索深度需大于评估 K,否则去重后不够 @10;
    # 多取候选不改变 chunk 级结果(评估时按 K 截断)。
    retrieval_depth = max(args.top_k, max(args.ks), 50)

    pairs: list[tuple[list[str], list[str]]] = []
    for s in tqdm(samples, desc="retrieve"):
        hits = retriever.search(s.question, top_k=retrieval_depth)
        pairs.append(build_pairs(hits, s, args.match_level))

    metrics = evaluate_batch(pairs, ks=tuple(args.ks))
    print("\n=== METRICS ===")
    for k, v in metrics.items():
        print(f"  {k:<10} = {v:.4f}")

    config = {
        "Embedding": settings.embedding_model,
        "Retriever": retriever_desc,
        "Reranker": "none",
        "LLM": "none (retrieval-only eval)",
        "Eval set": f"{args.eval} ({len(samples)} samples)",
        "Collection": args.collection,
        "Match level": args.match_level,
        "top_k": args.top_k,
    }
    path = append_phase_report(
        phase=args.phase,
        title=args.title,
        config=config,
        metrics=metrics,
        notes=args.notes,
    )
    print(f"\n[ OK ] appended to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
