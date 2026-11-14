"""API 测试夹具：AUK_DATA_DIR/AUK_MODELS_DIR 指向临时目录，绝不触碰真实 data/ 与 models/。

- 环境变量必须在导入 app.backend 之前设置（config.py 在导入时读取）。
- TestClient 不使用 with 上下文 → 不触发 lifespan → 不会拉起真实推理 worker。
"""
from __future__ import annotations

import io
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_TMP = Path(tempfile.mkdtemp(prefix="auk-api-tests-"))
os.environ["AUK_DATA_DIR"] = str(_TMP / "data")
os.environ["AUK_MODELS_DIR"] = str(_TMP / "models")
os.environ["AUK_LOGS_DIR"] = str(_TMP / "logs")
os.environ.pop("AUK_CAPABILITIES_FILE", None)
os.environ.pop("AUK_MODELS_REGISTRY", None)
os.environ.pop("AUK_MODEL_MANIFEST", None)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_wav(seconds: float = 1.0, sr: int = 24000, freq: float = 440.0) -> bytes:
    """合成正弦 WAV（16-bit mono），用于上传/拼接测试。"""
    buf = io.BytesIO()
    n = int(seconds * sr)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            v = int(12000 * math.sin(2 * math.pi * freq * i / sr))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return buf.getvalue()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.backend import db
    from app.backend.main import app

    db.init_db()
    return TestClient(app)  # 不用 with：不运行 lifespan，不启动 worker


@pytest.fixture(scope="session")
def audio(client):
    """上传一个合成 WAV，返回音频元数据。"""
    r = client.post("/api/audio/upload", files={"file": ("test.wav", io.BytesIO(make_wav(1.0)), "audio/wav")})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def fake_weights():
    """在临时 models 目录造出四个模型的全部文件（原始权重用稀疏文件匹配 manifest 大小）。

    仅测试探测/复用逻辑；不下载、不转换、不触碰真实 models/。
    """
    from app.backend import config, model_manager

    registry = model_manager.load_registry()
    manifest = model_manager.load_manifest()
    created = []
    for entry in registry["models"]:
        repo_manifest = manifest.get(entry["manifest_key"], {})
        for rel in entry.get("required_files", []) + entry.get("optional_files", []):
            p = config.MODELS_DIR / entry["raw_dir"] / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            size = int((repo_manifest.get(rel) or {}).get("size", 16))
            with open(p, "wb") as f:
                f.truncate(size)  # 稀疏文件：st_size 匹配 manifest，不占实际磁盘
            created.append(p)
        for rel in entry.get("converted_files", []) + entry.get("quantized_files", []):
            p = config.MODELS_DIR / "mlx-converted" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"fake-mlx")
            created.append(p)
    yield created
    for p in created:
        p.unlink(missing_ok=True)


@pytest.fixture()
def tiny_model_env(tmp_path, monkeypatch):
    """微型 registry + manifest（小文件、真实 sha256），用于 install/verify 执行测试。"""
    import hashlib
    import json

    models_dir = tmp_path / "models"
    raw = models_dir / "tiny"
    raw.mkdir(parents=True)
    content = b"auk-tiny-weights" * 100
    (raw / "a.bin").write_bytes(content)
    (raw / "LICENSE").write_text("MIT")
    mlx = models_dir / "mlx-converted"
    mlx.mkdir(parents=True)
    (mlx / "tiny.safetensors").write_bytes(b"converted")

    registry = {
        "licenses": {"mit-auk": {"id": "mit-auk", "name": "MIT", "url": "", "commercial": True, "summary": ""}},
        "models": [{
            "id": "tiny", "display_name": "Tiny", "family": "Test", "role": "main", "variant": "flash",
            "description": "", "source": {"repo": "Tencent-Hunyuan/AuK-Flash", "hf_repo": "tencent/AuK-Flash",
                                          "revision": "main", "urls": []},
            "license_id": "mit-auk", "raw_dir": "tiny", "manifest_key": "test/tiny",
            "required_files": ["a.bin", "LICENSE"], "optional_files": [],
            "converted_files": ["tiny.safetensors"], "quantized_files": [],
            "convert_steps": [], "quantize": None, "depends_on": [], "peak_memory_gb": None,
        }],
    }
    manifest = {"test/tiny": {
        "a.bin": {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()},
        "LICENSE": {"size": 3},
    }}
    reg_path = tmp_path / "registry.json"
    man_path = tmp_path / "manifest.json"
    reg_path.write_text(json.dumps(registry))
    man_path.write_text(json.dumps(manifest))
    monkeypatch.setenv("AUK_MODELS_REGISTRY", str(reg_path))
    monkeypatch.setenv("AUK_MODEL_MANIFEST", str(man_path))
    monkeypatch.setattr("app.backend.config.MODELS_DIR", models_dir)
    monkeypatch.setattr("app.backend.config.MLX_DIR", mlx)
    return {"models_dir": models_dir, "raw": raw, "mlx": mlx, "content": content,
            "registry": registry, "manifest": manifest}