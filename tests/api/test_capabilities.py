"""能力门禁：capabilities 读取、保守默认、not_supported 400、unverified note。"""
from __future__ import annotations

import io
import json

from conftest import make_wav


def test_capabilities_structure(client):
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "mlx"
    assert "speech_edit" in j["tasks"]
    assert j["tasks"]["speech_edit"]["state"] == "supported"
    assert j["tasks"]["speech_enhancement"]["state"] == "not_supported"
    assert "preferred_templates" in j


def test_capabilities_missing_file_conservative(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUK_CAPABILITIES_FILE", str(tmp_path / "nope.json"))
    j = client.get("/api/capabilities").json()
    assert j["tasks"]["speech_edit"]["state"] == "supported"
    assert j["tasks"]["zero_shot_tts"]["state"] == "supported"
    assert j["tasks"]["instruction_tts"]["state"] == "unverified"
    assert j["tasks"]["timbre_edit"]["state"] == "unverified"
    assert "未实测" in j["tasks"]["instruction_tts"]["note"]


def test_gate_not_supported_400(client, audio, tmp_path, monkeypatch):
    caps = client.get("/api/capabilities").json()
    caps["tasks"]["timbre_edit"]["state"] = "not_supported"
    p = tmp_path / "caps.json"
    p.write_text(json.dumps(caps))
    monkeypatch.setenv("AUK_CAPABILITIES_FILE", str(p))
    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "timbre", "description": "低沉男声",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "capability_not_supported"


def test_gate_unverified_allowed_with_note(client, audio):
    """emotion_edit 实测为 unverified：允许提交但 job 记录 note。"""
    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "emotion", "emotion": "开心",
    })
    assert r.status_code == 200
    j = r.json()
    assert "实验性" in j["note"]


def test_instruct_tts_supported(client):
    r = client.post("/api/jobs", json={
        "mode": "instruct_tts",
        "description": "一位二十多岁的女性，语气活泼开朗。",
        "target_text": "今天天气真好。",
    })
    assert r.status_code == 200
    j = r.json()
    assert j["audio_id"] is None
    assert j["kind"] == "infer"
    assert j["note"] == ""