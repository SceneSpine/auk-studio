#!/usr/bin/env bash
# 创建独立 Python 3.10 环境并安装 AuK[mlx] + Web 后端依赖。
# 不触碰系统 Python 或其他项目环境。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v uv >/dev/null || { echo "✗ 需要 uv（brew install uv）"; exit 1; }

MIRROR="${AUK_PYPI_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PROXY="${AUK_SOCKS_PROXY:-socks5h://127.0.0.1:7897}"

# 上游官方源码（不随本仓库分发；浅克隆，GitHub 必要时走代理）
if [ ! -d AuK/src/auk_mlx ]; then
  echo "→ 克隆上游 AuK（feat/mlx-apple-silicon，浅克隆）"
  HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY" ALL_PROXY="$PROXY" \
    git clone --depth 1 --branch feat/mlx-apple-silicon https://github.com/Tencent-Hunyuan/AuK.git AuK \
    || git clone --depth 1 --branch feat/mlx-apple-silicon https://github.com/Tencent-Hunyuan/AuK.git AuK
fi

# ckpts 符号链接（官方 quantize 按仓库根相对路径读 config；权重统一放 models/）
mkdir -p AuK/ckpts models
ln -sfn ../../models/auk-flash AuK/ckpts/AuK-Flash
ln -sfn ../../models/auk-base AuK/ckpts/AuK
ln -sfn ../../models/qwen-thinker AuK/ckpts/Qwen2.5-Omni-3B
ln -sfn ../../models/mlx-converted AuK/ckpts/mlx

if [ ! -x .venv-auk/bin/python ]; then
  echo "→ 创建 Python 3.10 虚拟环境 .venv-auk"
  # Python 构建包从 GitHub 下载，必要时走代理
  HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY" uv venv --python 3.10 .venv-auk || uv venv --python 3.10 .venv-auk
fi

echo "→ 安装 AuK[mlx] + 后端依赖（镜像: $MIRROR）"
uv pip install --python .venv-auk/bin/python --index-url "$MIRROR" \
  -e "./AuK[mlx]" "huggingface_hub[cli]" PySocks \
  fastapi "uvicorn[standard]" python-multipart

echo "→ 生成依赖快照 config/requirements-lock.txt"
uv pip freeze --python .venv-auk/bin/python > config/requirements-lock.txt

echo "→ MLX/Metal 最小测试"
.venv-auk/bin/python - <<'EOF'
import platform, mlx.core as mx
assert platform.machine() == "arm64", "需要 Apple Silicon"
assert mx.metal.is_available(), "Metal 不可用"
x = mx.random.normal((256, 256)); mx.eval(x @ x)
print(f"  ✓ arm64 | mlx {mx.__version__} | {mx.default_device()} | Metal 可用")
EOF

echo "✓ setup 完成。下一步：./scripts/download_models.sh && ./scripts/convert_models.sh"