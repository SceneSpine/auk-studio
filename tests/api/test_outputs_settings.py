"""输出评分/下载别名 + settings 白名单扩展。"""
from __future__ import annotations


def _upload_file_id(client, audio):
    from app.backend import db
    row = db.one(db.connect().execute("SELECT id FROM files WHERE audio_id=? AND kind='upload'", (audio["id"],)))
    return row["id"]


def test_rate_and_favorite(client, audio):
    fid = _upload_file_id(client, audio)
    r = client.post(f"/api/outputs/{fid}/rate", json={"rating": 5})
    assert r.status_code == 200
    assert r.json()["rating"] == 5
    r = client.post(f"/api/outputs/{fid}/rate", json={"favorite": True})
    assert r.json()["favorite"] == 1
    assert r.json()["rating"] == 5  # 未传 rating 保持不变
    r = client.post(f"/api/outputs/{fid}/rate", json={"rating": None, "favorite": False})
    assert r.json()["favorite"] == 0


def test_rate_out_of_range(client, audio):
    fid = _upload_file_id(client, audio)
    for bad in (0, 6, -1):
        r = client.post(f"/api/outputs/{fid}/rate", json={"rating": bad})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_rating"


def test_rate_unknown_file(client):
    assert client.post("/api/outputs/file_nope/rate", json={"rating": 3}).status_code == 404


def test_outputs_get_alias(client, audio):
    fid = _upload_file_id(client, audio)
    r1 = client.get(f"/api/files/{fid}")
    r2 = client.get(f"/api/outputs/{fid}")
    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content
    r3 = client.get(f"/api/outputs/{fid}", params={"download": 1})
    assert r3.status_code == 200
    assert "attachment" in r3.headers.get("content-disposition", "")
    assert client.get("/api/outputs/file_nope").status_code == 404


def test_settings_whitelist(client):
    r = client.put("/api/settings", json={
        "language": "en", "allow_update_check": "1", "default_variant": "base",
        "evil_key": "x", "theme": "dark",
    })
    assert r.status_code == 200
    j = client.get("/api/settings").json()
    assert j["language"] == "en"
    assert j["allow_update_check"] == "1"
    assert j["default_variant"] == "base"
    assert j["theme"] == "dark"
    assert "evil_key" not in j
    # 默认值
    assert client.get("/api/settings").json()["language"] in ("en", "zh-CN")


def test_settings_default_variant_validation(client):
    assert client.put("/api/settings", json={"default_variant": "foo"}).status_code == 400
    client.put("/api/settings", json={"default_variant": "flash", "language": "zh-CN", "allow_update_check": "0"})