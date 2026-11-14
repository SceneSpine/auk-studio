#!/usr/bin/env bash
# 按官方当前转换工具（src/auk_mlx/convert.py）把权重转换为 MLX 布局。
# 首版只转换 Flash 所需：VAE（Flash 自带）、DiT-flash、Thinker；并写 8-bit 量化副本。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv-auk/bin/python"
export PYTHONPATH="$ROOT/AuK/src"

FLASH="$ROOT/models/auk-flash"
QWEN="$ROOT/models/qwen-thinker"
MLX="$ROOT/models/mlx-converted"

for f in "$FLASH/vae.safetensors" "$FLASH/auk_flash.safetensors" "$FLASH/config.yaml" \
         "$QWEN/model-00001-of-00003.safetensors" "$QWEN/config.json"; do
  [ -f "$f" ] || { echo "✗ 缺少 $f —— 先运行 ./scripts/download_models.sh"; exit 1; }
done

free_gb=$(df -g "$ROOT" | awk 'NR==2{print $4}')
echo "→ 磁盘剩余 ${free_gb}GB（转换约需 22GB fp32 + 6GB q8）"
[ "$free_gb" -ge 30 ] || { echo "✗ 磁盘不足 30GB，终止"; exit 1; }

mkdir -p "$MLX" "$ROOT/logs"
exec > >(tee -a "$ROOT/logs/convert.log") 2>&1

# 复用检测：已存在的转换产物默认跳过（--force 强制重转）
FORCE=0; WITH_BASE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --with-base) WITH_BASE=1 ;;
  esac
done
need() { [ "$FORCE" = 1 ] || [ ! -f "$1" ]; }

if need "$MLX/vae.safetensors"; then
  echo "→ [1/4] 转换 VAE"
  "$PY" -m auk_mlx.convert vae "$FLASH/vae.safetensors" "$MLX/vae.safetensors"
else
  echo "→ [1/4] VAE 已存在，跳过（--force 可重转）"
fi
if need "$MLX/dit_flash.safetensors"; then
  echo "→ [2/4] 转换 DiT (Flash)"
  "$PY" -m auk_mlx.convert dit "$FLASH/auk_flash.safetensors" "$MLX/dit_flash.safetensors"
else
  echo "→ [2/4] DiT-flash 已存在，跳过"
fi
if need "$MLX/thinker/thinker.safetensors"; then
  echo "→ [3/4] 转换 Thinker (Qwen2.5-Omni-3B)"
  "$PY" -m auk_mlx.convert thinker "$QWEN" "$MLX/thinker"
else
  echo "→ [3/4] Thinker 已存在，跳过"
fi
if need "$MLX/dit_flash.q8.safetensors" || need "$MLX/thinker/thinker.q8.safetensors"; then
  echo "→ [4/4] 写 8-bit 量化副本（官方推荐精度）"
  "$PY" -m auk_mlx.convert quantize "$MLX" --bits 8 --variant flash
else
  echo "→ [4/4] 8-bit 副本已存在，跳过"
fi

# 可选：Base 对照模型（编辑跟随更准，速度较慢）
if [ "$WITH_BASE" = 1 ]; then
  BASE="$ROOT/models/auk-base"
  if [ -f "$BASE/auk_base.safetensors" ]; then
    if need "$MLX/dit_base.safetensors"; then
      echo "→ [Base] 转换 DiT (Base)"
      "$PY" -m auk_mlx.convert dit "$BASE/auk_base.safetensors" "$MLX/dit_base.safetensors"
    else
      echo "→ [Base] DiT-base 已存在，跳过"
    fi
    if need "$MLX/dit_base.q8.safetensors"; then
      echo "→ [Base] 写 8-bit 量化副本"
      "$PY" -m auk_mlx.convert quantize "$MLX" --bits 8 --variant base
    else
      echo "→ [Base] 8-bit 副本已存在，跳过"
    fi
  else
    echo "✗ Base 权重未下载：python3 scripts/download_models.py --only base"
    exit 1
  fi
fi

echo "→ 转换产物："
du -sh "$MLX"/* 2>/dev/null
echo "✓ 转换完成。可运行 ./scripts/start.sh 启动工作台。"