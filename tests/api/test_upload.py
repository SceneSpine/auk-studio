"""上传校验：类型/大小/时长/路径穿越。"""
from __future__ import annotations

import io
from pathlib import Path

from conftest import make_wav


def test_upload_wav_ok(client):
    r = client.post("/api/audio/upload", files={"file": ("hello.wav", io.BytesIO(make_wav(1.0)), "audio/wav")})
    assert r.status_code == 200
    j = r.json()
    assert j["duration"] > 0.9
    assert j["sample_rate"] == 24000
    assert j["waveform"]["points"]
    assert Path(j["stored_path"]).exists()


def test_upload_bad_ext(client):
    r = client.post("/api/audio/upload", files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
    assert r.status_code == 400


def test_upload_path_traversal_filename(client):
    """用户文件名不参与存储路径（随机 ID），穿越文件名必须被安全处理。"""
    r = client.post("/api/audio/upload",
                    files={"file": ("../../evil.wav", io.BytesIO(make_wav(0.6)), "audio/wav")})
    assert r.status_code == 200
    j = r.json()
    from app.backend import config
    stored = Path(j["stored_path"]).resolve()
    assert stored.is_relative_to(config.UPLOAD_DIR.resolve())
    assert ".." not in stored.name
    assert not (config.DATA_DIR.parent / "evil.wav").exists()


def test_upload_too_short(client):
    r = client.post("/api/audio/upload", files={"file": ("short.wav", io.BytesIO(make_wav(0.1)), "audio/wav")})
    assert r.status_code == 400


def test_upload_too_large(client, monkeypatch):
    from app.backend import config
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    r = client.post("/api/audio/upload", files={"file": ("big.wav", io.BytesIO(make_wav(0.5)), "audio/wav")})
    assert r.status_code == 413


def test_upload_not_audio(client):
    r = client.post("/api/audio/upload", files={"file": ("fake.wav", io.BytesIO(b"not a wav at all"), "audio/wav")})
    assert r.status_code == 400