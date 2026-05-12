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
from src.logger import logger
from src.retrieval.dense import DenseRetriever


DEFAULT_EVAL = Path("data/eval/eval_v1.jsonl")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", type=int, required=True)
    p.add_argument("--title", default="Dense Baseline", help="metrics.md 中的报告标题")
    p.add_argument("--eval", type=Path, default=DEFAULT_EVAL)
    p.add_argument("--collection", default=settings.milvus_collection)
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


def main() -> int:
    args = parse_args()

    samples = load_eval(args.eval)
    logger.info(f"loaded {len(samples)} eval samples from {args.eval}")

    retriever = DenseRetriever(collection_name=args.collection)

    pairs: list[tuple[list[str], list[str]]] = []
    for s in tqdm(samples, desc="retrieve"):
        hits = retriever.search(s.question, top_k=args.top_k)
        pairs.append(([h.id for h in hits], s.gold_doc_ids))

    metrics = evaluate_batch(pairs, ks=tuple(args.ks))
    print("\n=== METRICS ===")
    for k, v in metrics.items():
        print(f"  {k:<10} = {v:.4f}")

    config = {
        "Embedding": settings.embedding_model,
        "Retriever": f"DenseRetriever(BGE-M3 + Milvus HNSW M=16 efC=200, ef=64)",
        "Reranker": "none",
        "LLM": "none (retrieval-only eval)",
        "Eval set": f"{args.eval} ({len(samples)} samples)",
        "Collection": args.collection,
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
