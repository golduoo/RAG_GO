"""从 DuReader 段落语料随机采样,输出 Document jsonl(用于通用中文 RAG baseline)。

历史:原计划按物流关键词硬过滤,DuReader 命中仅 1816 条 < DoD 下限 5000。
变更:ADR-002 把项目改为"通用中文 RAG,以物流为 demo",改为随机采样 +
关键词作为 metadata 软标签(`is_logistics`)。

输入:  data/raw/dureader/data/corpus-*.parquet   (id, text)
输出:  data/processed/logistics_corpus.jsonl       (Document 模型)

用法:
    uv run python scripts/filter_logistics.py
    uv run python scripts/filter_logistics.py --target-size 6000 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

from src.ingest.schema import Document


DEFAULT_INPUT_GLOB = "data/raw/dureader/data/corpus-*.parquet"
DEFAULT_OUTPUT = Path("data/processed/logistics_corpus.jsonl")
DEFAULT_SOURCE_TAG = "C-MTEB/DuRetrieval"

# 物流软标签关键词(对齐 phase-1.md T1.3;不再硬过滤,只用于打标)
LOGISTICS_KEYWORDS: list[str] = [
    "快递", "物流", "运输", "包裹", "寄送", "海关",
    "赔付", "运单", "时效", "配送", "签收",
]
LOGISTICS_RE = re.compile("|".join(map(re.escape, LOGISTICS_KEYWORDS)))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument(
        "--target-size",
        type=int,
        default=8000,
        help="随机采样目标行数(默认 8000,落在 DoD [5000, 10000] 内)",
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--source-tag",
        default=DEFAULT_SOURCE_TAG,
        help="写入每条 Document 的 source 字段",
    )
    p.add_argument("--min-len", type=int, default=20, help="过短段落丢弃")
    p.add_argument("--max-len", type=int, default=2000, help="过长段落丢弃")
    return p.parse_args()


def iter_input_files(pattern: str) -> list[Path]:
    files = sorted(Path().glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files match: {pattern}")
    return files


def is_logistics(text: str) -> bool:
    return bool(LOGISTICS_RE.search(text))


def main() -> int:
    args = parse_args()
    random.seed(args.seed)

    files = iter_input_files(args.input_glob)
    print(f"input files ({len(files)}):")
    for f in files:
        print(f"  {f}  ({f.stat().st_size / 1024 / 1024:.2f} MB)")

    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    total = len(df)
    print(f"\ntotal rows: {total:,}")

    text_len = df["text"].str.len()
    df = df[(text_len >= args.min_len) & (text_len <= args.max_len)].reset_index(drop=True)
    after_len = len(df)
    print(f"after length filter [{args.min_len}, {args.max_len}]: {after_len:,}")

    # 分层采样:全保留物流命中,随机补齐非物流到 target_size
    logistics_mask_full = df["text"].apply(is_logistics)
    logistics_df = df[logistics_mask_full].reset_index(drop=True)
    other_df = df[~logistics_mask_full].reset_index(drop=True)
    print(f"logistics hits in corpus: {len(logistics_df):,}")
    print(f"non-logistics in corpus:  {len(other_df):,}")

    n_take = min(args.target_size, after_len)
    n_logi_keep = min(len(logistics_df), n_take)
    n_other_keep = max(0, n_take - n_logi_keep)
    other_idx = sorted(random.sample(range(len(other_df)), min(n_other_keep, len(other_df))))
    sampled = (
        pd.concat([logistics_df.iloc[:n_logi_keep], other_df.iloc[other_idx]], ignore_index=True)
        .sample(frac=1, random_state=args.seed)
        .reset_index(drop=True)
    )
    print(f"sampled total: {len(sampled):,}")

    logistics_mask = sampled["text"].apply(is_logistics)
    n_logistics = int(logistics_mask.sum())
    print(f"logistics-tagged subset: {n_logistics:,} ({n_logistics/len(sampled):.1%})")

    # 写 jsonl
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for i, row in sampled.iterrows():
            doc = Document(
                id=str(row["id"]),
                text=str(row["text"]),
                source=args.source_tag,
                metadata={
                    "corpus": "DuRetrieval",
                    "is_logistics": bool(logistics_mask.iloc[i]),
                },
            )
            fh.write(json.dumps(doc.model_dump(), ensure_ascii=False) + "\n")

    print(f"\n[ OK ] wrote {len(sampled):,} docs to {args.output}")
    if not (5000 <= len(sampled) <= 10000):
        print(
            f"[WARN] 行数 {len(sampled)} 不在 DoD 区间 [5000, 10000]",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
