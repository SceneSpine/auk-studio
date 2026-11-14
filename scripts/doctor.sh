#!/usr/bin/env bash
# 诊断：架构 / 系统 / 磁盘 / 内存 / 依赖 / Metal / 模型文件 / 权限 / 服务。
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

echo "=== 系统 ==="
[ "$(uname -m)" = "arm64" ] && ok "arm64" || bad "非 Apple Silicon"
echo "  macOS $(sw_vers -productVersion)"
free_gb=$(df -g "$ROOT" | awk 'NR==2{print $4}')
[ "$free_gb" -ge 30 ] && ok "磁盘剩余 ${free_gb}GB" || bad "磁盘剩余 ${free_gb}GB（建议 ≥30GB）"
lvl=$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null || echo 0)
[ "$lvl" -le 2 ] && ok "内存压力等级 $lvl" || bad "内存压力严重 ($lvl)，请关闭大内存应用"

echo "=== 工具 ==="
command -v ffmpeg >/dev/null && ok "ffmpeg $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)" || bad "ffmpeg 缺失"
command -v uv >/dev/null && ok "uv" || bad "uv 缺失"
command -v node >/dev/null && ok "node $(node --version)" || bad "node 缺失（前端构建需要）"

echo "=== Python 环境 ==="
PY="$ROOT/.venv-auk/bin/python"
if [ -x "$PY" ]; then
  ok ".venv-auk 存在"
  "$PY" - <<'EOF'
import sys
ok = True
try:
    import mlx.core as mx
    print(f"  ✓ mlx {mx.__version__} | device={mx.default_device()} | metal={mx.metal.is_available()}")
    if not mx.metal.is_available():
        print("  ✗ Metal 不可用"); ok = False
except Exception as e:
    print(f"  ✗ mlx 导入失败: {e}"); ok = False
for mod in ("torch", "transformers", "soundfile", "soxr", "fastapi", "auk_mlx"):
    try:
        __import__(mod)
        print(f"  ✓ {mod}")
    except Exception as e:
        print(f"  ✗ {mod}: {e}"); ok = False
sys.exit(0 if ok else 1)
EOF
  [ $? -eq 0 ] && PASS=$((PASS+1)) || FAIL=$((FAIL+1))
else
  bad ".venv-auk 缺失 —— 运行 ./scripts/setup.sh"
fi

echo "=== 模型文件 ==="
check() { [ -f "$1" ] && ok "$2 ($(du -h "$1" | cut -f1))" || bad "$2 缺失"; }
check models/auk-flash/auk_flash.safetensors "Flash DiT 原始权重"
check models/auk-flash/vae.safetensors "Flash VAE 原始权重"
check models/auk-flash/config.yaml "Flash config"
check models/qwen-thinker/model-00001-of-00003.safetensors "Qwen 分片 1"
check models/qwen-thinker/model-00002-of-00003.safetensors "Qwen 分片 2"
check models/qwen-thinker/model-00003-of-00003.safetensors "Qwen 分片 3"
check models/qwen-thinker/config.json "Qwen config"
check models/mlx-converted/vae.safetensors "MLX VAE"
check models/mlx-converted/dit_flash.safetensors "MLX DiT-flash"
check models/mlx-converted/fusion_flash.safetensors "MLX fusion-flash"
check models/mlx-converted/thinker/thinker.safetensors "MLX Thinker"

echo "=== 符号链接 ==="
for l in AuK-Flash Qwen2.5-Omni-3B mlx; do
  [ -L "AuK/ckpts/$l" ] && ok "AuK/ckpts/$l" || bad "AuK/ckpts/$l 符号链接缺失"
done

echo "=== 权限 ==="
for d in data logs models; do
  [ -w "$d" ] && ok "$d 可写" || bad "$d 不可写"
done

echo "=== 服务 ==="
if [ -f logs/backend.pid ] && kill -0 "$(cat logs/backend.pid)" 2>/dev/null; then
  ok "后端运行中 (pid $(cat logs/backend.pid))"
else
  echo "  · 后端未运行（./scripts/start.sh 启动）"
fi

echo ""
echo "结果: $PASS 项通过, $FAIL 项失败"
[ "$FAIL" -eq 0 ] && echo "✓ 环境健康" || echo "✗ 存在问题，请按上方提示修复"
exit "$FAIL"