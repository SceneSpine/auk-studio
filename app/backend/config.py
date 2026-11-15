"""AuK Local Studio 后端配置。所有路径默认相对项目根目录，可用环境变量覆盖。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _p(env: str, default: Path) -> Path:
    v = os.environ.get(env)
    return Path(v).expanduser().resolve() if v else default


DATA_DIR = _p("AUK_DATA_DIR", ROOT / "data")
MODELS_DIR = _p("AUK_MODELS_DIR", ROOT / "models")
LOGS_DIR = _p("AUK_LOGS_DIR", ROOT / "logs")
AUK_REPO = _p("AUK_REPO", ROOT / "AuK")


def _default_venv_python() -> Path:
    # venv 布局：Windows 为 Scripts/python.exe，POSIX 为 bin/python（可用 AUK_VENV_PYTHON 覆盖）
    if os.name == "nt":
        return ROOT / ".venv-auk" / "Scripts" / "python.exe"
    return ROOT / ".venv-auk" / "bin" / "python"


VENV_PYTHON = _p("AUK_VENV_PYTHON", _default_venv_python())

UPLOAD_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"
OUTPUT_DIR = DATA_DIR / "outputs"
WAVEFORM_DIR = DATA_DIR / "waveform-cache"
TEMP_DIR = DATA_DIR / "temp"
DB_PATH = DATA_DIR / "studio.db"

FLASH_DIR = MODELS_DIR / "auk-flash"
BASE_DIR = MODELS_DIR / "auk-base"
QWEN_DIR = MODELS_DIR / "qwen-thinker"
MLX_DIR = MODELS_DIR / "mlx-converted"

HOST = os.environ.get("AUK_HOST", "127.0.0.1")
PORT = int(os.environ.get("AUK_PORT", "7860"))

# 上传限制（首版可配置）
MAX_UPLOAD_MB = int(os.environ.get("AUK_MAX_UPLOAD_MB", "200"))
MAX_DURATION_S = float(os.environ.get("AUK_MAX_DURATION_S", "600"))
ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".aiff", ".aif", ".mp4"}

# 推理默认参数（以官方 MLX 实现实际支持为准）
DEFAULT_BITS = int(os.environ.get("AUK_DEFAULT_BITS", "8"))  # 官方建议 8-bit；4-bit 中文退化
DEFAULT_SEQUENTIAL = os.environ.get("AUK_DEFAULT_SEQUENTIAL", "0") == "1"
MODEL_IDLE_UNLOAD_S = int(os.environ.get("AUK_MODEL_IDLE_UNLOAD_S", "900"))  # 空闲自动卸载
WORKER_POLL_S = float(os.environ.get("AUK_WORKER_POLL_S", "1.0"))

# 拼接导出
DEFAULT_CROSSFADE_MS = int(os.environ.get("AUK_DEFAULT_CROSSFADE_MS", "30"))

for d in (UPLOAD_DIR, JOBS_DIR, OUTPUT_DIR, WAVEFORM_DIR, TEMP_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)