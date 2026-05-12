#!/usr/bin/env bash
# 下载 DuReader 段落语料 → data/raw/dureader/
# 这是 download_data.py 的薄封装,Linux/Mac/Git-Bash 可用
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python scripts/download_data.py "$@"
