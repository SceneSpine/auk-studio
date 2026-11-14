#!/usr/bin/env bash
# 下载 AuK-Flash + Qwen2.5-Omni-3B 权重（ModelScope 官方渠道，HF sha256 校验，断点续传）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/logs"
python3 "$ROOT/scripts/download_models.py" "$@" 2>&1 | tee -a "$ROOT/logs/download.log"