"""从 HuggingFace 下载 DuReader 段落语料(用于物流子集筛选)。

默认数据集:`C-MTEB/DuRetrieval`(CMTEB 基准,含约 10 万条中文段落)。
下载到:`data/raw/dureader/`

国内用户:huggingface_hub 1.x 与 hf-mirror.com 不兼容(严格校验响应域名),
所以这里直接走 HTTPS GET 下载文件,通过 `--endpoint` / `HF_ENDPOINT` 控制源站。

用法:
    uv run python scripts/download_data.py
    uv run python scripts/download_data.py --endpoint https://huggingface.co
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from tqdm import tqdm


DEFAULT_DATASET = "C-MTEB/DuRetrieval"
DEFAULT_OUTDIR = Path("data/raw/dureader")
DEFAULT_ENDPOINT = "https://hf-mirror.com"

# DuRetrieval 的语料文件列表(从 HF API list_repo_files 得到,固定不变)
FILES: list[str] = [
    "README.md",
    "data/corpus-00000-of-00001-19b9e924cb33e4d5.parquet",
    "data/queries-00000-of-00001-7c7edb40be6b560c.parquet",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default=DEFAULT_DATASET)
    p.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    p.add_argument(
        "--endpoint",
        default=os.getenv("HF_ENDPOINT", DEFAULT_ENDPOINT),
        help="HuggingFace 镜像或官方域名",
    )
    return p.parse_args()


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> None:
    """单文件流式下载,带进度条。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with (
            open(dest, "wb") as fh,
            tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=dest.name,
            ) as bar,
        ):
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
                    bar.update(len(chunk))


def main() -> int:
    args = parse_args()
    endpoint = args.endpoint.rstrip("/")
    print(f"endpoint = {endpoint}")
    print(f"dataset  = {args.dataset}")
    print(f"outdir   = {args.outdir.resolve()}")

    args.outdir.mkdir(parents=True, exist_ok=True)

    for relpath in FILES:
        url = f"{endpoint}/datasets/{args.dataset}/resolve/main/{relpath}"
        dest = args.outdir / relpath
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[SKIP] {relpath} 已存在 ({dest.stat().st_size / 1024 / 1024:.2f} MB)")
            continue
        print(f"[GET ] {url}")
        try:
            download_file(url, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {relpath}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

    print("\n目录内容:")
    for p in sorted(args.outdir.rglob("*")):
        if p.is_file():
            size_mb = p.stat().st_size / 1024 / 1024
            print(f"  {p.relative_to(args.outdir)}  ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
