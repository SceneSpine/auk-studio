"""音色库：consent 强制、CRUD、归档、删除不删音频。"""
from __future__ import annotations

from pathlib import Path


def test_voice_consent_required(client, audio):
    r = client.post("/api/voices", json={"name": "无确认", "audio_id": audio["id"]})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "voice_consent_required"
    r = client.post("/api/voices", json={"name": "假确认", "audio_id": audio["id"], "consent_confirmed": False})
    assert r.status_code == 403


def test_voice_crud(client, audio):
    r = client.post("/api/voices", json={
        "name": "测试音色", "description": "合成男声", "tags": ["test", "male"],
        "audio_id": audio["id"], "consent_confirmed": True,
    })
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["consent"]["confirmed"] is True
    assert v["consent"]["statement"] == "我确认对该参考声音拥有合法使用权，仅在本机用于非商业研究/评估用途"
    assert v["consent"]["confirmed_at"] > 0
    assert v["tags"] == ["test", "male"]
    assert v["audio"]["id"] == audio["id"]
    assert v["archived"] is False

    lst = client.get("/api/voices").json()
    assert any(x["id"] == v["id"] for x in lst)

    # archive / unarchive
    r = client.post(f"/api/voices/{v['id']}/archive", json={"archived": True})
    assert r.json()["archived"] is True
    assert not any(x["id"] == v["id"] for x in client.get("/api/voices").json())
    assert any(x["id"] == v["id"] for x in client.get("/api/voices", params={"include_archived": True}).json())
    r = client.post(f"/api/voices/{v['id']}/archive", json={"archived": False})
    assert r.json()["archived"] is False

    # 删除记录但保留音频文件
    stored = Path(audio["stored_path"])
    assert stored.exists()
    r = client.delete(f"/api/voices/{v['id']}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert stored.exists(), "删除音色不得删除音频文件"
    from app.backend import db
    assert db.get_audio(audio["id"]) is not None
    assert client.delete(f"/api/voices/{v['id']}").status_code == 404


def test_voice_requires_existing_audio(client):
    r = client.post("/api/voices", json={"name": "x", "audio_id": "aud_nope", "consent_confirmed": True})
    assert r.status_code == 404


def test_voice_empty_name(client, audio):
    r = client.post("/api/voices", json={"name": "  ", "audio_id": audio["id"], "consent_confirmed": True})
    assert r.status_code in (400, 422)