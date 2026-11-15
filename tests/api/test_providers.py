"""在线 TTS provider（v0.3）：CRUD、key 掩码、base_url 校验、test 端点、
在线 job 创建校验与全流程（线程版 mock 服务器返回真实 WAV，worker 函数直接调用）。

不触外网：mock 绑定 127.0.0.1 随机端口；不加载本地模型。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.backend import config, db, providers, worker

from mock_tts import mock_tts

KEY = "sk-test-secret-1234567890abcd"  # 尾 4 位 abcd
KEY2 = "sk-other-key-0987654321wxyz"  # 尾 4 位 wxyz


def _create(client, **kw) -> dict:
    payload = {
        "name": "Mock TTS", "kind": "openai_tts", "base_url": "https://api.example.com/v1",
        "api_key": KEY, "model": "mock-tts-1", "voice": "alloy", **kw,
    }
    r = client.post("/api/providers", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _online_job(client, pid: str, **kw) -> dict:
    payload = {"provider_id": pid, "mode": "tts", "target_text": "你好，这是一条在线合成测试。", **kw}
    r = client.post("/api/jobs", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- CRUD + key 掩码 ----------------

def test_create_and_masking(client):
    r = client.post("/api/providers", json={
        "name": "OpenAI", "kind": "openai_tts", "base_url": "https://api.openai.com/v1",
        "api_key": KEY, "model": "gpt-4o-mini-tts", "voice": "alloy",
    })
    assert r.status_code == 200, r.text
    p = r.json()
    assert KEY not in r.text  # 响应绝不出现完整 key
    assert p["has_key"] is True
    assert p["key_masked"] == "…abcd"
    assert p["enabled"] is True
    assert p["kind"] == "openai_tts"
    assert p["base_url"] == "https://api.openai.com/v1"
    assert p["model"] == "gpt-4o-mini-tts" and p["voice"] == "alloy"
    assert p["id"].startswith("prov_") and p["created_at"] > 0
    assert "api_key" not in p
    # 清理
    assert client.delete(f"/api/providers/{p['id']}").status_code == 200


def test_list_and_local_shape(client):
    p = _create(client)
    r = client.get("/api/providers")
    assert r.status_code == 200
    data = r.json()
    assert KEY not in r.text
    assert any(x["id"] == p["id"] for x in data["providers"])
    # 测试环境无模型权重 → local.available=False
    assert data["local"] == {"id": "local", "name": "本地 MLX", "available": False}
    client.delete(f"/api/providers/{p['id']}")


def test_update_and_delete(client):
    p = _create(client)
    r = client.put(f"/api/providers/{p['id']}", json={"name": "改名后的服务商"})
    assert r.status_code == 200
    assert r.json()["name"] == "改名后的服务商"
    assert KEY not in r.text
    r = client.delete(f"/api/providers/{p['id']}")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert all(x["id"] != p["id"] for x in client.get("/api/providers").json()["providers"])
    assert client.delete(f"/api/providers/{p['id']}").status_code == 404
    assert client.put(f"/api/providers/{p['id']}", json={"name": "x"}).status_code == 404
    assert client.post(f"/api/providers/{p['id']}/test").status_code == 404


# ---------------- base_url 校验（防 SSRF） ----------------

@pytest.mark.parametrize("url", [
    "http://192.168.1.10/v1",
    "http://10.0.0.5:8080/v1",
    "http://172.16.0.1/v1",
    "http://169.254.169.254/latest",
    "http://evil.example.com/v1",
    "http://localhost.evil.com/v1",
    "http://127.0.0.1.nip.io/v1",
    "ftp://api.example.com/v1",
    "not-a-url",
    "",
    "https://",
    "https://user:pass@api.example.com/v1",
    "https://api.example.com/v1?x=1",
])
def test_base_url_invalid_rejected(client, url):
    r = client.post("/api/providers", json={
        "name": "bad", "kind": "openai_tts", "base_url": url,
        "api_key": KEY, "model": "m", "voice": "v",
    })
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "invalid_provider"


@pytest.mark.parametrize("url", [
    "https://api.openai.com/v1",
    "https://api.siliconflow.cn/v1",
    "http://127.0.0.1:7899/v1",
    "http://localhost:8080/v1",
])
def test_base_url_valid_accepted(client, url):
    p = _create(client, base_url=url)
    assert p["base_url"] == url
    client.delete(f"/api/providers/{p['id']}")


def test_base_url_trailing_slash_normalized(client):
    p = _create(client, base_url="https://api.example.com/v1/")
    assert p["base_url"] == "https://api.example.com/v1"
    client.delete(f"/api/providers/{p['id']}")


def test_validate_base_url_unit():
    assert providers.validate_base_url("https://x.example/v1/") == "https://x.example/v1"
    assert providers.validate_base_url("http://localhost:9/v1") == "http://localhost:9/v1"
    with pytest.raises(ValueError):
        providers.validate_base_url("http://192.168.0.1/v1")
    with pytest.raises(ValueError):
        providers.validate_base_url("http://127.0.0.1:99999/v1")  # 非法端口


# ---------------- 必填校验 ----------------

@pytest.mark.parametrize("missing", ["name", "base_url", "model", "voice"])
def test_create_missing_required(client, missing):
    payload = {"name": "x", "kind": "openai_tts", "base_url": "https://api.example.com/v1",
               "api_key": KEY, "model": "m", "voice": "v"}
    del payload[missing]
    assert client.post("/api/providers", json=payload).status_code == 422


def test_create_blank_name_and_bad_kind(client):
    r = client.post("/api/providers", json={
        "name": "   ", "kind": "openai_tts", "base_url": "https://api.example.com/v1",
        "model": "m", "voice": "v",
    })
    assert r.status_code == 400
    r = client.post("/api/providers", json={
        "name": "x", "kind": "other_kind", "base_url": "https://api.example.com/v1",
        "model": "m", "voice": "v",
    })
    assert r.status_code == 422


# ---------------- PUT 空 key 不改 ----------------

def test_put_empty_key_keeps_existing(client):
    p = _create(client)
    pid = p["id"]
    for body in ({"api_key": "", "name": "空串不改"}, {"api_key": None}, {"name": "缺省不改"}):
        r = client.put(f"/api/providers/{pid}", json=body)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["has_key"] is True
        assert out["key_masked"] == "…abcd"
        assert KEY not in r.text
    # 显式换 key → 掩码变化
    r = client.put(f"/api/providers/{pid}", json={"api_key": KEY2})
    assert r.json()["key_masked"] == "…wxyz"
    assert KEY2 not in r.text
    client.delete(f"/api/providers/{pid}")


def test_put_enabled_and_validation(client):
    p = _create(client)
    r = client.put(f"/api/providers/{p['id']}", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = client.put(f"/api/providers/{p['id']}", json={"base_url": "http://10.0.0.1/v1"})
    assert r.status_code == 400
    # 失败的 PUT 不影响原值
    cur = next(x for x in client.get("/api/providers").json()["providers"] if x["id"] == p["id"])
    assert cur["base_url"] == "https://api.example.com/v1"
    assert cur["enabled"] is False
    client.delete(f"/api/providers/{p['id']}")


# ---------------- key 掩码 / 脱敏单元 ----------------

def test_mask_key_unit():
    assert providers.mask_key("") == ""
    assert providers.mask_key(None) == ""
    assert providers.mask_key("abc") == "…"  # 过短不泄露
    assert providers.mask_key("abcd") == "…"
    assert providers.mask_key("sk-1234abcd") == "…abcd"


def test_redact_unit():
    assert providers.redact(f"key={KEY} end", KEY) == "key=[REDACTED] end"
    assert providers.redact("no key here", KEY) == "no key here"
    assert providers.redact("text", "") == "text"


# ---------------- test 端点（本地 mock） ----------------

def test_test_endpoint_ok(client):
    with mock_tts(required_key=KEY) as srv:
        p = _create(client, base_url=srv.base_url)
        r = client.post(f"/api/providers/{p['id']}/test")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["ok"] is True
        assert isinstance(out["latency_ms"], int) and out["latency_ms"] >= 0
        assert KEY not in r.text
        assert len(srv.requests) == 1
        req = srv.requests[0]
        assert req["body"]["input"] == "test"
        assert req["body"]["response_format"] == "wav"
        assert req["body"]["model"] == "mock-tts-1"
        assert req["body"]["voice"] == "alloy"
        assert req["headers"].get("authorization") == f"Bearer {KEY}"
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_no_key(client):
    with mock_tts() as srv:  # 不要求鉴权
        p = _create(client, base_url=srv.base_url, api_key="")
        assert p["has_key"] is False and p["key_masked"] == ""
        r = client.post(f"/api/providers/{p['id']}/test")
        assert r.json()["ok"] is True
        assert "authorization" not in srv.requests[0]["headers"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_bad_key(client):
    with mock_tts(required_key="sk-the-right-key-0000000000") as srv:
        p = _create(client, base_url=srv.base_url)  # 携带错误 key
        r = client.post(f"/api/providers/{p['id']}/test")
        out = r.json()
        assert out["ok"] is False
        assert "401" in out["error"]
        assert KEY not in out["error"]
        assert KEY not in r.text
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_server_error(client):
    with mock_tts(fail_status=500, fail_message="mock internal error") as srv:
        p = _create(client, base_url=srv.base_url)
        out = client.post(f"/api/providers/{p['id']}/test").json()
        assert out["ok"] is False
        assert "500" in out["error"] and "mock internal error" in out["error"]
        assert KEY not in out["error"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_unreachable(client):
    p = _create(client, base_url="http://127.0.0.1:9/v1")  # 端口 9：连接拒绝
    out = client.post(f"/api/providers/{p['id']}/test").json()
    assert out["ok"] is False
    assert out["error"]
    assert out["latency_ms"] is not None
    client.delete(f"/api/providers/{p['id']}")


# ---------------- 在线 job 创建校验 ----------------

def test_online_job_mode_must_be_tts(client, audio):
    p = _create(client)
    for mode in ("replace", "full", "custom", "instruct_tts", "timbre", "emotion"):
        r = client.post("/api/jobs", json={
            "provider_id": p["id"], "mode": mode, "target_text": "x",
            "audio_id": audio["id"], "description": "d", "emotion": "平静",
            "segment": {"original": "a", "replacement": "b"}, "instruction": "i",
        })
        assert r.status_code == 400, (mode, r.text)
    client.delete(f"/api/providers/{p['id']}")


def test_online_job_requires_text(client):
    p = _create(client)
    r = client.post("/api/jobs", json={"provider_id": p["id"], "mode": "tts", "target_text": "  "})
    assert r.status_code == 400
    client.delete(f"/api/providers/{p['id']}")


def test_online_job_provider_unknown_or_disabled(client):
    r = client.post("/api/jobs", json={"provider_id": "prov_nope", "mode": "tts", "target_text": "x"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider_not_found"
    p = _create(client)
    client.put(f"/api/providers/{p['id']}", json={"enabled": False})
    r = client.post("/api/jobs", json={"provider_id": p["id"], "mode": "tts", "target_text": "x"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "provider_disabled"
    client.delete(f"/api/providers/{p['id']}")


def test_online_job_ignores_local_params(client, audio):
    p = _create(client)
    j = _online_job(client, p["id"], audio_id=audio["id"], bits=8, seed=42,
                    gen_seconds=10, nfe=16, model_variant="base", voice_id="voice_whatever")
    assert j["provider_id"] == p["id"]
    assert j["mode"] == "tts"
    assert j["audio_id"] is None
    assert j["bits"] is None and j["seed"] is None and j["gen_seconds"] is None
    assert j["nfe"] is None and j["voice_id"] is None
    assert j["status"] == "queued"
    client.delete(f"/api/providers/{p['id']}")


def test_local_jobs_provider_id_default(client, audio):
    for extra in ({}, {"provider_id": "local"}, {"provider_id": ""}):
        r = client.post("/api/jobs", json={
            "audio_id": audio["id"], "mode": "full", "target_text": "本地回归", **extra,
        })
        assert r.status_code == 200, r.text
        assert r.json()["provider_id"] is None


# ---------------- 在线 job 全流程（mock + worker 直接调用） ----------------

def test_online_job_full_flow(client):
    with mock_tts(required_key=KEY, wav_seconds=1.0) as srv:
        p = _create(client, base_url=srv.base_url)
        j = _online_job(client, p["id"])
        jid = j["id"]
        holder = worker.EngineHolder()
        worker.run_job(db.get_job(jid), holder)  # 路由入口：在线分支
        assert holder.engine is None  # 未加载本地模型

        done = db.get_job(jid)
        assert done["status"] == "completed", done["error"]
        assert done["provider_id"] == p["id"]
        assert done["rtf"] is None and done["peak_memory_gb"] is None
        assert done["elapsed_s"] and done["elapsed_s"] > 0
        assert abs(done["output_duration"] - 1.0) < 0.1
        out = Path(done["output_path"])
        assert out.exists() and out.name == f"{jid}_candidate.wav"
        assert out.read_bytes()[:4] == b"RIFF"  # 真实 WAV

        # mock 收到正确的请求
        req = srv.requests[-1]
        assert req["body"]["input"] == "你好，这是一条在线合成测试。"
        assert req["body"]["model"] == "mock-tts-1"
        assert req["body"]["voice"] == "alloy"
        assert req["body"]["response_format"] == "wav"
        assert req["headers"].get("authorization") == f"Bearer {KEY}"

        # candidate 文件 + 音频记录注册（同 instruct_tts，可存音色库）
        detail = client.get(f"/api/jobs/{jid}").json()
        cands = [f for f in detail["files"] if f["kind"] == "candidate"]
        assert len(cands) == 1
        aid = cands[0]["audio_id"]
        assert aid
        a = client.get(f"/api/audio/{aid}").json()
        assert abs(a["duration"] - 1.0) < 0.1
        assert a["sample_rate"] == 24000
        r = client.post("/api/voices", json={
            "name": "在线候选音色", "audio_id": aid, "consent_confirmed": True,
        })
        assert r.status_code == 200, r.text

        # GET /api/jobs 含 provider_id
        lst = client.get("/api/jobs").json()
        assert next(x for x in lst if x["id"] == jid)["provider_id"] == p["id"]

        # key 掩码：响应与日志绝不出现完整 key
        assert KEY not in client.get(f"/api/jobs/{jid}").text
        assert KEY not in client.get(f"/api/jobs/{jid}/logs").text
        assert KEY not in (config.JOBS_DIR / jid / "job.log").read_text()
        assert KEY not in client.get("/api/providers").text
        client.delete(f"/api/providers/{p['id']}")


def test_online_job_mp3_content_type(client):
    # Content-Type=audio/mpeg → 存 .mp3（mock 仍返回可解码音频字节，ffprobe 嗅探真实格式）
    with mock_tts(required_key=KEY, content_type="audio/mpeg") as srv:
        p = _create(client, base_url=srv.base_url)
        j = _online_job(client, p["id"])
        worker.run_online_tts(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "completed", done["error"]
        assert done["output_path"].endswith(f"{j['id']}_candidate.mp3")
        assert Path(done["output_path"]).exists()
        assert done["output_duration"] > 0
        client.delete(f"/api/providers/{p['id']}")


def test_online_job_http_error_redacted(client):
    with mock_tts(required_key=KEY, fail_status=429,
                  fail_message="Rate limit reached for requests") as srv:
        p = _create(client, base_url=srv.base_url)
        j = _online_job(client, p["id"])
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "429" in done["error"]
        assert "Rate limit" in done["error"]
        assert KEY not in done["error"]
        assert KEY not in (config.JOBS_DIR / j["id"] / "job.log").read_text()
        # 失败可重试（旧端点语义不变）
        assert client.post(f"/api/jobs/{j['id']}/retry").status_code == 200
        assert db.get_job(j["id"])["status"] == "queued"
        client.post(f"/api/jobs/{j['id']}/cancel")
        client.delete(f"/api/providers/{p['id']}")


def test_online_job_cancel_before_request(client):
    with mock_tts(required_key=KEY) as srv:
        p = _create(client, base_url=srv.base_url)
        j = _online_job(client, p["id"])
        db.update_job(j["id"], cancel_requested=1)
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "cancelled"
        assert done["output_path"] is None
        assert len(srv.requests) == 0  # 未发出请求
        client.delete(f"/api/providers/{p['id']}")


def test_online_job_cancel_during_request(client):
    with mock_tts(required_key=KEY) as srv:
        p = _create(client, base_url=srv.base_url)
        j = _online_job(client, p["id"])
        # 请求到达服务器时置取消标志：请求不可中断 → 阶段边界处理，候选仍保留
        srv.on_request = lambda body: db.update_job(j["id"], cancel_requested=1)
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "cancelled"
        assert len(srv.requests) == 1
        assert done["output_path"] and Path(done["output_path"]).exists()
        client.delete(f"/api/providers/{p['id']}")


def test_online_job_provider_deleted_fails(client):
    p = _create(client, base_url="https://api.example.com/v1")
    j = _online_job(client, p["id"])
    client.delete(f"/api/providers/{p['id']}")
    worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
    done = db.get_job(j["id"])
    assert done["status"] == "failed"
    assert "不存在" in done["error"]