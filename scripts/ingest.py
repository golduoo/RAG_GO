"""端到端入库脚本:jsonl Documents → split → embed → 双写 Milvus + ES。

用法:
    uv run python scripts/ingest.py
    uv run python scripts/ingest.py --limit 100 --drop --collection chunks_v1_test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from tqdm import tqdm

from src.config import settings
from src.ingest.indexer import (
    DEFAULT_BATCH_SIZE,
    BGEEmbedder,
    ESWriter,
    MilvusWriter,
)
from src.ingest.multi_granularity import MultiGranularitySplitter
from src.ingest.schema import Chunk, Document
from src.ingest.splitters import FixedTokenSplitter
from src.logger import logger


DEFAULT_INPUT = Path("data/processed/logistics_corpus.jsonl")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--collection", default=settings.milvus_collection)
    p.add_argument("--es-index", default=settings.es_index)
    p.add_argument("--drop", action="store_true", help="清空已有 collection / index")
    p.add_argument(
        "--limit", type=int, default=0, help="只处理前 N 条 Document(0 = 全部)"
    )
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--chunk-size", type=int, default=400)
    p.add_argument("--chunk-overlap", type=int, default=50)
    p.add_argument(
        "--splitter",
        choices=("fixed", "multi"),
        default="fixed",
        help="fixed=FixedTokenSplitter(Phase1) / multi=MultiGranularitySplitter(Phase2)",
    )
    p.add_argument(
        "--sentence-max", type=int, default=150, help="multi: 句子级最大字符数"
    )
    p.add_argument("--use-ik", action="store_true", help="ES 用 ik_smart(需已装插件)")
    return p.parse_args()


def build_splitter(args: argparse.Namespace):
    if args.splitter == "multi":
        return MultiGranularitySplitter(
            paragraph_size=args.chunk_size,
            paragraph_overlap=args.chunk_overlap,
            sentence_max=args.sentence_max,
        )
    return FixedTokenSplitter(
        chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap
    )


def load_documents(path: Path, limit: int = 0) -> list[Document]:
    docs: list[Document] = []
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if limit and i >= limit:
                break
            data = json.loads(line)
            docs.append(Document(**data))
    return docs


def batched(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def main() -> int:
    args = parse_args()
    t0 = time.time()

    logger.info(f"loading {args.input}")
    docs = load_documents(args.input, args.limit)
    logger.info(f"loaded {len(docs)} documents")

    splitter = build_splitter(args)
    t_split = time.time()
    chunks: list[Chunk] = splitter.split_documents(docs)
    dist = Counter(c.granularity for c in chunks)
    logger.info(
        f"split into {len(chunks)} chunks ({time.time() - t_split:.1f}s) "
        f"splitter={args.splitter} granularity={dict(dist)}"
    )

    if not chunks:
        logger.error("no chunks produced, aborting")
        return 1

    embedder = BGEEmbedder()
    milvus = MilvusWriter(collection_name=args.collection, drop_existing=args.drop)
    es = ESWriter(index_name=args.es_index, drop_existing=args.drop, use_ik=args.use_ik)

    n_milvus = 0
    n_es = 0
    t_embed_total = 0.0
    t_write_total = 0.0

    for batch in tqdm(list(batched(chunks, args.batch_size)), desc="embed+write"):
        texts = [c.text for c in batch]
        t = time.time()
        vectors = embedder.encode(texts, batch_size=args.batch_size)
        t_embed_total += time.time() - t

        t = time.time()
        n_milvus += milvus.insert(batch, vectors)
        n_es += es.insert(batch)
        t_write_total += time.time() - t

    milvus_count = milvus.flush()
    es_count = es.refresh()

    elapsed = time.time() - t0
    logger.info(
        f"DONE: {len(chunks)} chunks | milvus={milvus_count} es={es_count} "
        f"| embed={t_embed_total:.1f}s write={t_write_total:.1f}s total={elapsed:.1f}s"
    )

    ok = milvus_count == es_count == len(chunks)
    if not ok:
        logger.error(
            f"COUNT MISMATCH: chunks={len(chunks)} milvus={milvus_count} es={es_count}"
        )
        return 2
    print(
        f"\n[ OK ] chunks={len(chunks)}  milvus={milvus_count}  es={es_count}"
        f"  embed={t_embed_total:.1f}s  total={elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
