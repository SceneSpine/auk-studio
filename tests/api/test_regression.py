"""旧端点回归：health/system/model/audio/jobs（splice/trim/accept/cancel/retry）/files/settings。"""
from __future__ import annotations

import io
from pathlib import Path

from conftest import make_wav


def test_health_system_model(client):
    assert client.get("/api/health").json()["status"] == "ok"
    s = client.get("/api/system").json()
    assert s["memory"]["total_gb"] > 0
    assert "worker" in s and "paths" in s
    ms = client.get("/api/model/status").json()
    assert "downloaded" in ms and "files" in ms and "license_note" in ms
    assert client.post("/api/model/unload").json()["ok"] is True


def test_audio_endpoints(client, audio):
    aid = audio["id"]
    assert any(a["id"] == aid for a in client.get("/api/audio").json())
    assert client.get(f"/api/audio/{aid}").json()["id"] == aid
    w = client.get(f"/api/audio/{aid}/waveform").json()
    assert w["points"] and w["duration"] > 0
    # Range 流式 206
    r = client.get(f"/api/audio/{aid}/stream", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert len(r.content) == 100
    assert r.headers["Content-Range"].startswith("bytes 0-99/")
    # 全量 200
    assert client.get(f"/api/audio/{aid}/stream").status_code == 200
    # 无效 Range 416
    assert client.get(f"/api/audio/{aid}/stream", headers={"Range": "bytes=999999999-"}).status_code == 416
    assert client.get("/api/audio/aud_nope").status_code == 404


def test_job_lifecycle_cancel_retry_delete(client, audio):
    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "replace",
        "segment": {"original": "会议室", "replacement": "发布会"},
        "model_variant": "flash", "bits": 8, "seed": 42,
    })
    jid = r.json()["id"]
    assert r.json()["status"] == "queued"
    assert client.get(f"/api/jobs/{jid}").json()["audio"]["id"] == audio["id"]
    assert client.get(f"/api/jobs/{jid}/logs").json()["lines"] == []
    # 排队取消
    assert client.post(f"/api/jobs/{jid}/cancel").json()["state"] == "cancelled"
    # 终态再取消 → 409
    assert client.post(f"/api/jobs/{jid}/cancel").status_code == 409
    # 重试 → queued
    assert client.post(f"/api/jobs/{jid}/retry").json()["status"] == "queued"
    # accept 标记
    assert client.post(f"/api/jobs/{jid}/accept", json={"accepted": True}).json()["ok"] is True
    # 删除
    assert client.delete(f"/api/jobs/{jid}").json()["ok"] is True
    assert client.get(f"/api/jobs/{jid}").status_code == 404


def test_splice_trim_result(client, audio):
    """构造一个已完成任务（候选为合成 WAV），验证拼接/片段/结果/下载链路。"""
    from app.backend import config, db

    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "replace",
        "segment": {"original": "会议室", "replacement": "发布会"},
    })
    jid = r.json()["id"]
    cand = config.OUTPUT_DIR / f"{jid}_candidate.wav"
    cand.write_bytes(make_wav(1.0))
    db.update_job(jid, status="completed", output_path=str(cand), output_duration=1.0)
    db.register_file(cand, "candidate", job_id=jid, audio_id=audio["id"], label="生成候选（整段）")

    # splice：未修改区域保留原始 PCM
    r = client.post(f"/api/jobs/{jid}/splice", json={"start_s": 0.3, "end_s": 0.7})
    assert r.status_code == 200, r.text
    spliced = r.json()
    assert spliced["file_id"]
    assert Path(db.get_file(spliced["file_id"])["path"]).exists()
    assert client.get(f"/api/files/{spliced['file_id']}").status_code == 200
    # trim
    r = client.post(f"/api/jobs/{jid}/trim", json={"start_s": 0.2, "end_s": 0.8})
    assert r.status_code == 200
    trimmed = r.json()
    assert abs(trimmed["duration"] - 0.6) < 0.05
    # 非法区间
    assert client.post(f"/api/jobs/{jid}/trim", json={"start_s": 0.8, "end_s": 0.2}).status_code == 400
    # result
    res = client.get(f"/api/jobs/{jid}/result").json()
    assert res["job"]["id"] == jid
    assert len(res["files"]) >= 3
    assert all("url" in f for f in res["files"])
    # 下载文件名安全化
    r = client.get(f"/api/files/{trimmed['file_id']}", params={"download": 1})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    # 清理
    client.delete(f"/api/jobs/{jid}")


def test_audio_delete_reference_guard(client, audio):
    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "full", "target_text": "引用守卫",
    })
    jid = r.json()["id"]
    assert client.delete(f"/api/audio/{audio['id']}").status_code == 409
    client.delete(f"/api/jobs/{jid}")


def test_files_path_safety(client):
    """files 表路径越界必须 403（_safe_data_path）。"""
    from app.backend import db
    fid = db.register_file("/etc/passwd", "candidate", label="evil")
    assert client.get(f"/api/files/{fid}").status_code == 403
    assert client.get(f"/api/outputs/{fid}").status_code == 403


def test_settings_legacy_keys(client):
    j = client.get("/api/settings").json()
    for k in ("theme", "crossfade_ms", "default_bits", "default_sequential", "idle_unload_s"):
        assert k in j