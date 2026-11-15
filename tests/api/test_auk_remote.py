"""auk_remote 远程 AuK 全能力推理：job 路由校验（全 7 模式）+ worker 全链路。

mock 远程 AuK 服务器（mock_auk）实现 /api/health、/api/audio/upload、/api/jobs、
/api/jobs/{id}、/api/jobs/{id}/result、/api/files/{id}，返回真实 WAV。
worker 函数直接调用（不启动真实 worker、不加载本地模型、不触外网）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.backend import config, db, providers, worker

from mock_auk import mock_auk

KEY = "sk-test-secret-1234567890abcd"  # 尾 4 位 abcd


def _create_remote(client, base_url: str, **kw) -> dict:
    payload = {"name": "远程 AuK", "kind": "auk_remote", "base_url": base_url, "api_key": KEY, **kw}
    r = client.post("/api/providers", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _mode_payload(mode: str, audio_id: str) -> dict:
    """各模式的合法必填字段。"""
    if mode == "replace":
        return {"audio_id": audio_id, "segment": {"original": "会议室", "replacement": "发布会"}}
    if mode == "full":
        return {"audio_id": audio_id, "target_text": "全文替换的目标台词"}
    if mode == "custom":
        return {"audio_id": audio_id, "instruction": "把语速放慢一点"}
    if mode == "tts":
        return {"audio_id": audio_id, "target_text": "零样本合成台词"}
    if mode == "instruct_tts":
        return {"description": "温柔的年轻女声", "target_text": "指令合成台词"}
    if mode == "timbre":
        return {"audio_id": audio_id, "description": "低沉的中年男声"}
    if mode == "emotion":
        return {"audio_id": audio_id, "emotion": "开心"}
    raise AssertionError(mode)


def _job(client, pid: str, mode: str, audio_id: str, **kw) -> dict:
    payload = {"provider_id": pid, "mode": mode, **_mode_payload(mode, audio_id), **kw}
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- job 路由校验：全 7 模式放行 ----------------

@pytest.mark.parametrize("mode", ["replace", "full", "custom", "tts", "instruct_tts", "timbre", "emotion"])
def test_all_modes_accepted(client, audio, mode):
    with mock_auk() as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], mode, audio["id"], bits=8, seed=42, gen_seconds=6.0,
                 nfe=16, model_variant="base", original_text="原文")
        assert j["provider_id"] == p["id"]
        assert j["mode"] == mode
        assert j["status"] == "queued"
        assert j["bits"] == 8 and j["seed"] == 42 and j["gen_seconds"] == 6.0
        assert j["nfe"] == 16 and j["model_variant"] == "base"
        if mode == "instruct_tts":
            assert j["audio_id"] is None
        else:
            assert j["audio_id"] == audio["id"]
        assert "127.0.0.1" in j["note"]  # 隐私提示：远程 host
        client.delete(f"/api/providers/{p['id']}")


@pytest.mark.parametrize("mode,drop", [
    ("replace", "segment"), ("full", "target_text"), ("custom", "instruction"),
    ("tts", "target_text"), ("instruct_tts", "description"), ("timbre", "description"),
])
def test_mode_missing_required_rejected(client, audio, mode, drop):
    with mock_auk() as srv:
        p = _create_remote(client, srv.base_url)
        payload = {"provider_id": p["id"], "mode": mode, **_mode_payload(mode, audio["id"])}
        del payload[drop]
        r = client.post("/api/jobs", json=payload)
        assert r.status_code == 400, (mode, r.text)
        client.delete(f"/api/providers/{p['id']}")


def test_mode_missing_audio_rejected(client):
    with mock_auk() as srv:
        p = _create_remote(client, srv.base_url)
        for mode in ("replace", "full", "custom", "tts", "timbre", "emotion"):
            payload = {"provider_id": p["id"], "mode": mode, **_mode_payload(mode, "aud_nope")}
            if mode == "tts":
                payload.pop("audio_id")  # tts 无参考音频
            r = client.post("/api/jobs", json=payload)
            assert r.status_code in (400, 404), (mode, r.text)
        # emotion 非法值
        r = client.post("/api/jobs", json={"provider_id": p["id"], "mode": "emotion",
                                           "audio_id": "aud_nope", "emotion": "不存在的情绪"})
        assert r.status_code == 400
        client.delete(f"/api/providers/{p['id']}")


def test_provider_unknown_or_disabled(client, audio):
    r = client.post("/api/jobs", json={"provider_id": "prov_nope", "mode": "replace",
                                       "audio_id": audio["id"],
                                       "segment": {"original": "a", "replacement": "b"}})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider_not_found"
    with mock_auk() as srv:
        p = _create_remote(client, srv.base_url)
        client.put(f"/api/providers/{p['id']}", json={"enabled": False})
        r = client.post("/api/jobs", json={"provider_id": p["id"], "mode": "tts",
                                           "audio_id": audio["id"], "target_text": "x"})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "provider_disabled"
        client.delete(f"/api/providers/{p['id']}")


def test_local_jobs_provider_id_default(client, audio):
    # 本地链路零回归：provider_id 缺省/local/空串 → 本地任务
    for extra in ({}, {"provider_id": "local"}, {"provider_id": ""}):
        r = client.post("/api/jobs", json={
            "audio_id": audio["id"], "mode": "full", "target_text": "本地回归", **extra,
        })
        assert r.status_code == 200, r.text
        assert r.json()["provider_id"] is None


# ---------------- worker 全链路：上传 → 创建 → 轮询 → 下载 ----------------

def test_remote_replace_full_flow(client, audio):
    with mock_auk(required_key=KEY, wav_seconds=1.0, polls_before_done=2) as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        jid = j["id"]
        holder = worker.EngineHolder()
        worker.run_job(db.get_job(jid), holder)  # 路由入口：远程分支
        assert holder.engine is None  # 未加载本地模型

        done = db.get_job(jid)
        assert done["status"] == "completed", done["error"]
        assert done["provider_id"] == p["id"]
        assert done["rtf"] is None and done["peak_memory_gb"] is None
        assert done["elapsed_s"] and done["elapsed_s"] > 0
        assert abs(done["output_duration"] - 1.0) < 0.1
        assert "127.0.0.1" in done["note"]  # note 记远程 host
        out = Path(done["output_path"])
        assert out.exists() and out.name == f"{jid}_candidate.wav"
        assert out.read_bytes()[:4] == b"RIFF"  # 真实 WAV

        # 远程收到的请求序列：upload → create → poll×N → result → file
        paths = [(r["method"], r["path"]) for r in srv.requests]
        remote_jid = list(srv.jobs)[0]
        assert paths[0] == ("POST", "/api/audio/upload")
        assert paths[1] == ("POST", "/api/jobs")
        assert ("GET", f"/api/jobs/{remote_jid}") in paths
        assert ("GET", f"/api/jobs/{remote_jid}/result") in paths
        assert any(m == "GET" and pa.startswith("/api/files/") for m, pa in paths)

        # 上传字节 = 本地 normalized wav 字节
        up = srv.requests[0]
        assert up["upload_name"].endswith(".wav")
        remote_aid = list(srv.uploads)[0]
        norm = Path(audio["normalized_path"] or audio["stored_path"]).read_bytes()
        assert srv.uploads[remote_aid] == norm

        # 创建 payload：mode/segment/audio_id 正确；不传 voice_id/provider_id
        create = srv.requests[1]["body"]
        assert create["mode"] == "replace"
        assert create["segment"] == {"original": "会议室", "replacement": "发布会"}
        assert create["audio_id"] == remote_aid
        assert "voice_id" not in create and "provider_id" not in create
        assert all(r["headers"].get("authorization") == f"Bearer {KEY}" for r in srv.requests)

        # candidate 注册：有输入音频 → 复用其 audio_id（同本地）
        detail = client.get(f"/api/jobs/{jid}").json()
        cands = [f for f in detail["files"] if f["kind"] == "candidate"]
        assert len(cands) == 1
        assert cands[0]["audio_id"] == audio["id"]

        # GET /api/jobs 含 provider_id
        lst = client.get("/api/jobs").json()
        assert next(x for x in lst if x["id"] == jid)["provider_id"] == p["id"]

        # key 掩码：响应与日志绝不出现完整 key
        assert KEY not in client.get(f"/api/jobs/{jid}").text
        assert KEY not in client.get(f"/api/jobs/{jid}/logs").text
        assert KEY not in (config.JOBS_DIR / jid / "job.log").read_text()
        assert KEY not in client.get("/api/providers").text
        client.delete(f"/api/providers/{p['id']}")


def test_remote_instruct_tts_skips_upload(client):
    with mock_auk(required_key=KEY, wav_seconds=0.8) as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "instruct_tts", "")
        worker.run_remote_auk(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "completed", done["error"]
        # 无输入音频 → 不上传
        assert all(r["path"] != "/api/audio/upload" for r in srv.requests)
        create = next(r for r in srv.requests if r["path"] == "/api/jobs" and r["method"] == "POST")["body"]
        assert "audio_id" not in create
        assert create["description"] == "温柔的年轻女声"
        assert create["target_text"] == "指令合成台词"
        # 无输入音频 → 候选注册为新音频记录（可存音色库）
        detail = client.get(f"/api/jobs/{j['id']}").json()
        cands = [f for f in detail["files"] if f["kind"] == "candidate"]
        aid = cands[0]["audio_id"]
        assert aid and aid != ""
        a = client.get(f"/api/audio/{aid}").json()
        assert abs(a["duration"] - 0.8) < 0.1
        r = client.post("/api/voices", json={"name": "远程候选音色", "audio_id": aid,
                                             "consent_confirmed": True})
        assert r.status_code == 200, r.text
        client.delete(f"/api/providers/{p['id']}")


def test_remote_tts_voice_id_resolved(client, audio):
    with mock_auk(required_key=KEY) as srv:
        p = _create_remote(client, srv.base_url)
        r = client.post("/api/voices", json={"name": "参考音色", "audio_id": audio["id"],
                                             "consent_confirmed": True})
        assert r.status_code == 200, r.text
        vid = r.json()["id"]
        j = _job(client, p["id"], "tts", "", voice_id=vid)
        assert j["audio_id"] == audio["id"]  # 路由解析 voice_id → audio_id
        worker.run_remote_auk(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "completed", done["error"]
        # voice_id 解析为本地音频再上传
        assert any(r["path"] == "/api/audio/upload" for r in srv.requests)
        create = next(r for r in srv.requests if r["path"] == "/api/jobs" and r["method"] == "POST")["body"]
        assert create["audio_id"] in srv.uploads
        assert "voice_id" not in create
        client.delete(f"/api/providers/{p['id']}")


def test_remote_mp3_content_type(client, audio):
    # Content-Type=audio/mpeg → 存 .mp3（ffprobe 嗅探真实格式）
    with mock_auk(content_type="audio/mpeg") as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_remote_auk(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "completed", done["error"]
        assert done["output_path"].endswith(f"{j['id']}_candidate.mp3")
        assert Path(done["output_path"]).exists()
        assert done["output_duration"] > 0
        client.delete(f"/api/providers/{p['id']}")


# ---------------- 远程失败 / 超时 ----------------

def test_remote_job_failed(client, audio):
    with mock_auk(fail_job_error="远程推理显存不足") as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "远程推理显存不足" in done["error"]
        # 失败可重试（旧端点语义不变）
        assert client.post(f"/api/jobs/{j['id']}/retry").status_code == 200
        assert db.get_job(j["id"])["status"] == "queued"
        client.post(f"/api/jobs/{j['id']}/cancel")
        client.delete(f"/api/providers/{p['id']}")


def test_remote_create_http_error_redacted(client, audio):
    # 错误消息注入完整 key → 必须脱敏
    with mock_auk(fail_create=429, fail_message=f"Rate limit reached for {KEY}") as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "429" in done["error"]
        assert "Rate limit" in done["error"]
        assert KEY not in done["error"]
        assert "[REDACTED]" in done["error"]
        assert KEY not in (config.JOBS_DIR / j["id"] / "job.log").read_text()
        client.delete(f"/api/providers/{p['id']}")


def test_remote_upload_error(client, audio):
    with mock_auk(fail_upload=413) as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_remote_auk(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "413" in done["error"]
        # 上传失败 → 未创建远程任务
        assert all(r["path"] != "/api/jobs" or r["method"] != "POST" for r in srv.requests)
        client.delete(f"/api/providers/{p['id']}")


def test_remote_timeout(client, audio, monkeypatch):
    monkeypatch.setattr(providers, "REMOTE_TIMEOUT_S", 0.5)
    monkeypatch.setattr(providers, "REMOTE_POLL_S", 0.05)
    with mock_auk(hang=True) as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_remote_auk(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "超时" in done["error"]
        # 超时后尽力远程取消
        assert any(r["method"] == "POST" and r["path"].endswith("/cancel") for r in srv.requests)
        client.delete(f"/api/providers/{p['id']}")


def test_remote_provider_deleted_fails(client, audio):
    with mock_auk() as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        client.delete(f"/api/providers/{p['id']}")
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "不存在" in done["error"]


# ---------------- 取消 ----------------

def test_remote_cancel_before_request(client, audio):
    with mock_auk() as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        db.update_job(j["id"], cancel_requested=1)
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "cancelled"
        assert done["output_path"] is None
        assert len(srv.requests) == 0  # 未发出请求
        client.delete(f"/api/providers/{p['id']}")


def test_remote_cancel_during_poll(client, audio, monkeypatch):
    monkeypatch.setattr(providers, "REMOTE_POLL_S", 0.05)
    with mock_auk(polls_before_done=100) as srv:
        p = _create_remote(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])

        def on_request(method, path, body):
            # 首次轮询到达时置取消标志
            if method == "GET" and path.startswith("/api/jobs/") and not path.endswith("/result"):
                db.update_job(j["id"], cancel_requested=1)

        srv.on_request = on_request
        worker.run_remote_auk(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "cancelled"
        assert done["output_path"] is None
        # 尽力 POST 远程 cancel
        assert any(r["method"] == "POST" and r["path"].endswith("/cancel") for r in srv.requests)
        remote_job = list(srv.jobs.values())[0]
        assert remote_job["status"] == "cancelled"
        client.delete(f"/api/providers/{p['id']}")