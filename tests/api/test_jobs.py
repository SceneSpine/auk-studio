"""POST /api/jobs 各 mode 必填校验、voice 引用、kind 过滤。"""
from __future__ import annotations


def test_replace_requires_segment(client, audio):
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "replace"})
    assert r.status_code == 400
    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "replace",
        "segment": {"original": "会议室", "replacement": "发布会"},
    })
    assert r.status_code == 200


def test_full_requires_text(client, audio):
    assert client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "full"}).status_code == 400
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "full", "target_text": "新台词"})
    assert r.status_code == 200


def test_custom_requires_instruction(client, audio):
    assert client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "custom"}).status_code == 400
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "custom", "instruction": "放慢语速"})
    assert r.status_code == 200


def test_tts_requires_reference_and_text(client, audio):
    assert client.post("/api/jobs", json={"mode": "tts", "target_text": "你好"}).status_code == 400
    assert client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "tts"}).status_code == 400
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "tts", "target_text": "你好世界"})
    assert r.status_code == 200


def test_instruct_tts_requires_description_and_text(client):
    assert client.post("/api/jobs", json={"mode": "instruct_tts", "target_text": "你好"}).status_code == 400
    assert client.post("/api/jobs", json={"mode": "instruct_tts", "description": "女声"}).status_code == 400


def test_timbre_requires_audio_and_description(client, audio):
    assert client.post("/api/jobs", json={"mode": "timbre", "description": "低沉"}).status_code == 400
    assert client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "timbre"}).status_code == 400
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "timbre", "description": "低沉男声"})
    assert r.status_code == 200


def test_emotion_enum(client, audio):
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "emotion", "emotion": "狂喜"})
    assert r.status_code == 400
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "emotion", "emotion": "平静"})
    assert r.status_code == 200


def test_unknown_audio_404(client):
    r = client.post("/api/jobs", json={"audio_id": "aud_nonexistent", "mode": "full", "target_text": "x"})
    assert r.status_code == 404


def test_invalid_bits(client, audio):
    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "full", "target_text": "x", "bits": 5,
    })
    assert r.status_code == 400


def test_invalid_mode_rejected(client, audio):
    r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "enhance"})
    assert r.status_code == 422  # pydantic pattern


def test_install_kind_rejected_via_jobs(client):
    r = client.post("/api/jobs", json={"mode": "full", "target_text": "x", "kind": "install"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_kind"


def test_voice_reference(client, audio):
    r = client.post("/api/voices", json={
        "name": "参考音色", "audio_id": audio["id"], "consent_confirmed": True,
    })
    assert r.status_code == 200
    vid = r.json()["id"]
    # tts 用 voice_id 作参考（无 audio_id）
    r = client.post("/api/jobs", json={"mode": "tts", "target_text": "你好", "voice_id": vid})
    assert r.status_code == 200
    assert r.json()["audio_id"] == audio["id"]
    assert r.json()["voice_id"] == vid
    # 归档后不可用
    client.post(f"/api/voices/{vid}/archive", json={"archived": True})
    r = client.post("/api/jobs", json={"mode": "tts", "target_text": "你好", "voice_id": vid})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "voice_archived"
    # 不存在的音色
    r = client.post("/api/jobs", json={"mode": "tts", "target_text": "你好", "voice_id": "voice_nope"})
    assert r.status_code == 404


def test_jobs_kind_filter(client, audio):
    client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "full", "target_text": "过滤测试"})
    r = client.get("/api/jobs", params={"kind": "infer"})
    assert r.status_code == 200
    assert all(j["kind"] == "infer" for j in r.json())
    r = client.get("/api/jobs", params={"kind": "install"})
    assert all(j["kind"] == "install" for j in r.json())