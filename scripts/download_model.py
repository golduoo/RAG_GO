"""从 HuggingFace 直链下载模型权重(绕过 hf_hub 1.x 严格域名校验)。

用法:
    uv run python scripts/download_model.py BAAI/bge-m3 --outdir models/bge-m3
    uv run python scripts/download_model.py BAAI/bge-reranker-v2-m3 --outdir models/bge-reranker-v2-m3
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from tqdm import tqdm


DEFAULT_ENDPOINT = "https://hf-mirror.com"

# 不下载的目录/文件(图片、onnx 等占空间但用不到)
SKIP_PREFIXES = ("imgs/", "onnx/", ".gitattributes")
SKIP_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".md5")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo_id")
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument(
        "--endpoint",
        default=os.getenv("HF_ENDPOINT", DEFAULT_ENDPOINT),
    )
    return p.parse_args()


def list_files(repo_id: str, endpoint: str) -> list[str]:
    from huggingface_hub import HfApi

    api = HfApi(endpoint=endpoint)
    files = api.list_repo_files(repo_id, repo_type="model")
    return [
        f for f in files
        if not f.startswith(SKIP_PREFIXES) and not f.lower().endswith(SKIP_EXTS)
    ]


def download_file(url: str, dest: Path, chunk: int = 1 << 14) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as resp:
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
            for piece in resp.iter_content(chunk_size=chunk):
                if piece:
                    fh.write(piece)
                    bar.update(len(piece))


def main() -> int:
    args = parse_args()
    endpoint = args.endpoint.rstrip("/")
    print(f"endpoint = {endpoint}")
    print(f"repo     = {args.repo_id}")
    print(f"outdir   = {args.outdir.resolve()}")

    args.outdir.mkdir(parents=True, exist_ok=True)
    files = list_files(args.repo_id, endpoint)
    print(f"files to download: {len(files)}")

    for rel in files:
        url = f"{endpoint}/{args.repo_id}/resolve/main/{rel}"
        dest = args.outdir / rel
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[SKIP] {rel}")
            continue
        try:
            download_file(url, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {rel}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

    print(f"\n[ OK ] all files downloaded to {args.outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
