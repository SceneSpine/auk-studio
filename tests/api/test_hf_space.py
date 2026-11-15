"""hf_space（HuggingFace AuK Space，Gradio 6）：provider CRUD / 参数映射 / worker 全链路 /
取消 / 超时 / 脱敏 / 代理配置解析 / test 端点。

mock Space（mock_gradio）实现 /gradio_api/info、/gradio_api/upload、
/gradio_api/call/generate_with_pe（POST + SSE）、/gradio_api/file={path}，返回真实 WAV。
worker 函数直接调用（不启动真实 worker、不加载本地模型、不触外网）。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import socks

from app.backend import config, db, providers, worker

from mock_gradio import mock_gradio

KEY = "hf-test-secret-1234567890abcd"  # 尾 4 位 abcd


def _create_space(client, base_url: str, **kw) -> dict:
    payload = {"name": "HF AuK Space", "kind": "hf_space", "base_url": base_url, "api_key": KEY, **kw}
    r = client.post("/api/providers", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _mode_payload(mode: str, audio_id: str) -> dict:
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


def _call_data(srv) -> list:
    """取唯一一次 call 的 data 数组（8 参）。"""
    assert len(srv.calls) == 1, srv.calls
    return next(iter(srv.calls.values()))["data"]


# ---------------- provider CRUD：kind=hf_space ----------------

def test_create_hf_space_and_masking(client):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        assert p["kind"] == "hf_space"
        assert p["model"] == "" and p["voice"] == ""
        assert p["has_key"] is True and p["key_masked"] == "…abcd"
        assert KEY not in client.get("/api/providers").text
        client.delete(f"/api/providers/{p['id']}")


def test_create_hf_space_key_optional(client):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url, api_key="")
        assert p["has_key"] is False and p["key_masked"] == ""
        client.delete(f"/api/providers/{p['id']}")


def test_create_hf_space_ignores_model_voice(client):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url, model="x", voice="y")
        assert p["model"] == "" and p["voice"] == ""
        client.delete(f"/api/providers/{p['id']}")


def test_bad_kind_rejected(client):
    r = client.post("/api/providers", json={"name": "x", "kind": "openai_tts",
                                            "base_url": "https://x.hf.space"})
    assert r.status_code == 422


# ---------------- job 路由：全 7 模式放行 ----------------

@pytest.mark.parametrize("mode", ["replace", "full", "custom", "tts", "instruct_tts", "timbre", "emotion"])
def test_all_modes_accepted(client, audio, mode):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], mode, audio["id"], bits=8, seed=42, gen_seconds=6.0,
                 nfe=16, model_variant="base")
        assert j["provider_id"] == p["id"] and j["mode"] == mode and j["status"] == "queued"
        if mode == "instruct_tts":
            assert j["audio_id"] is None
        else:
            assert j["audio_id"] == audio["id"]
        assert "127.0.0.1" in j["note"] and "HF Space" in j["note"]
        client.delete(f"/api/providers/{p['id']}")


def test_local_jobs_unaffected(client, audio):
    # 本地链路零回归：provider_id 缺省/local → 本地任务
    for extra in ({}, {"provider_id": "local"}):
        r = client.post("/api/jobs", json={"audio_id": audio["id"], "mode": "full",
                                           "target_text": "本地回归", **extra})
        assert r.status_code == 200, r.text
        assert r.json()["provider_id"] is None


# ---------------- 参数映射（8 参，顺序固定） ----------------

def test_param_mapping_base(client, audio):
    with mock_gradio(required_key=KEY) as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"], model_variant="base",
                 seed=7, nfe=16, gen_seconds=6.0)
        worker.run_hf_space(db.get_job(j["id"]))
        assert db.get_job(j["id"])["status"] == "completed", db.get_job(j["id"])["error"]
        use_pe, variant, audio_fd, instruction, gen_seconds, nfe, cfg, seed = _call_data(srv)
        assert use_pe is False
        assert variant == "AuK (Base)"
        assert audio_fd["meta"] == {"_type": "gradio.FileData"} and audio_fd["path"]
        assert "会议室" in instruction and "发布会" in instruction
        assert gen_seconds == 6.0 and nfe == 16 and cfg == 2.0 and seed == 7
        # final_instruction 与发送一致
        assert db.get_job(j["id"])["final_instruction"] == instruction
        client.delete(f"/api/providers/{p['id']}")


def test_param_mapping_flash(client, audio):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"], model_variant="flash",
                 seed=99, nfe=64, gen_seconds=5.0)
        worker.run_hf_space(db.get_job(j["id"]))
        assert db.get_job(j["id"])["status"] == "completed"
        use_pe, variant, _audio, _instr, _gs, nfe, cfg, seed = _call_data(srv)
        assert use_pe is False and variant == "AuK-Flash ⚡"
        assert nfe == 4 and cfg == 0 and seed == 99  # flash 固定 nfe=4/cfg=0，忽略 job.nfe
        client.delete(f"/api/providers/{p['id']}")


def test_param_defaults(client, audio):
    # seed/nfe 缺省 → seed=42、base nfe=32；gen_seconds None → 0（自动）
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"], model_variant="base")
        worker.run_hf_space(db.get_job(j["id"]))
        assert db.get_job(j["id"])["status"] == "completed"
        _u, _v, _a, _i, gen_seconds, nfe, cfg, seed = _call_data(srv)
        assert gen_seconds == 0.0 and nfe == 32 and cfg == 2.0 and seed == 42
        client.delete(f"/api/providers/{p['id']}")


def test_gen_seconds_clamped(client, audio):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"], gen_seconds=120.0)
        worker.run_hf_space(db.get_job(j["id"]))
        assert db.get_job(j["id"])["status"] == "completed"
        assert _call_data(srv)[4] == 30.0  # 钳制到 30
        client.delete(f"/api/providers/{p['id']}")


def test_instruct_tts_template_and_null_audio(client):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "instruct_tts", "")
        worker.run_hf_space(db.get_job(j["id"]))
        assert db.get_job(j["id"])["status"] == "completed"
        _u, _v, audio_fd, instruction, *_ = _call_data(srv)
        assert audio_fd is None  # 无音频 → null
        assert instruction.startswith("Based on the following description:")
        assert "温柔的年轻女声" in instruction and "指令合成台词" in instruction
        # 无上传
        assert all(r["path"] != "/gradio_api/upload" for r in srv.requests)
        client.delete(f"/api/providers/{p['id']}")


def test_full_uses_english_tts_template(client, audio):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "full", audio["id"])
        worker.run_hf_space(db.get_job(j["id"]))
        assert db.get_job(j["id"])["status"] == "completed"
        assert _call_data(srv)[3].startswith("Say the following with the same voice:")
        client.delete(f"/api/providers/{p['id']}")


# ---------------- worker 全链路：upload → call → SSE → download ----------------

def test_hf_replace_full_flow(client, audio):
    with mock_gradio(required_key=KEY, wav_seconds=1.0) as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        jid = j["id"]
        holder = worker.EngineHolder()
        worker.run_job(db.get_job(jid), holder)  # 路由入口：hf_space 分支
        assert holder.engine is None  # 未加载本地模型

        done = db.get_job(jid)
        assert done["status"] == "completed", done["error"]
        assert done["provider_id"] == p["id"]
        assert done["rtf"] is None and done["peak_memory_gb"] is None
        assert done["elapsed_s"] and done["elapsed_s"] > 0
        assert abs(done["output_duration"] - 1.0) < 0.1
        assert "127.0.0.1" in done["note"] and "HF Space" in done["note"]
        out = Path(done["output_path"])
        assert out.exists() and out.name == f"{jid}_candidate.wav"
        assert out.read_bytes()[:4] == b"RIFF"

        # 请求序列：upload → call(POST) → SSE(GET) → file(GET)
        paths = [(r["method"], r["path"]) for r in srv.requests]
        eid = next(iter(srv.calls))
        assert paths[0] == ("POST", "/gradio_api/upload")
        assert paths[1] == ("POST", "/gradio_api/call/generate_with_pe")
        assert ("GET", f"/gradio_api/call/generate_with_pe/{eid}") in paths
        assert any(m == "GET" and pa.startswith("/gradio_api/file=") for m, pa in paths)

        # 上传字节 = 本地 normalized wav
        up = srv.requests[0]
        assert up["upload_name"].endswith(".wav")
        norm = Path(audio["normalized_path"] or audio["stored_path"]).read_bytes()
        assert next(iter(srv.uploads.values())) == norm

        # 所有请求携带 Bearer
        assert all(r["headers"].get("authorization") == f"Bearer {KEY}" for r in srv.requests)

        # candidate 注册：有输入音频 → 复用其 audio_id
        detail = client.get(f"/api/jobs/{jid}").json()
        cands = [f for f in detail["files"] if f["kind"] == "candidate"]
        assert len(cands) == 1 and cands[0]["audio_id"] == audio["id"]

        # key 掩码：响应与日志绝不出现完整 key
        assert KEY not in client.get(f"/api/jobs/{jid}").text
        assert KEY not in client.get(f"/api/jobs/{jid}/logs").text
        assert KEY not in (config.JOBS_DIR / jid / "job.log").read_text()
        assert KEY not in client.get("/api/providers").text
        client.delete(f"/api/providers/{p['id']}")


def test_hf_instruct_tts_registers_new_audio(client):
    with mock_gradio(wav_seconds=0.8) as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "instruct_tts", "")
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "completed", done["error"]
        detail = client.get(f"/api/jobs/{j['id']}").json()
        cands = [f for f in detail["files"] if f["kind"] == "candidate"]
        aid = cands[0]["audio_id"]
        assert aid and aid != ""
        a = client.get(f"/api/audio/{aid}").json()
        assert abs(a["duration"] - 0.8) < 0.1
        # 可存音色库
        r = client.post("/api/voices", json={"name": "HF 候选音色", "audio_id": aid,
                                             "consent_confirmed": True})
        assert r.status_code == 200, r.text
        client.delete(f"/api/providers/{p['id']}")


def test_hf_tts_voice_id_resolved(client, audio):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        r = client.post("/api/voices", json={"name": "参考音色", "audio_id": audio["id"],
                                             "consent_confirmed": True})
        vid = r.json()["id"]
        j = _job(client, p["id"], "tts", "", voice_id=vid)
        assert j["audio_id"] == audio["id"]
        worker.run_hf_space(db.get_job(j["id"]))
        assert db.get_job(j["id"])["status"] == "completed"
        assert any(r["path"] == "/gradio_api/upload" for r in srv.requests)
        assert _call_data(srv)[2] is not None  # voice_id 解析为音频再上传
        client.delete(f"/api/providers/{p['id']}")


def test_hf_file_fallback_without_url(client, audio):
    # FileData 无 url → 回退 {base}/gradio_api/file={path}
    with mock_gradio(omit_url=True) as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_hf_space(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "completed", done["error"]
        assert any(m == "GET" and pa.startswith("/gradio_api/file=") for m, pa in
                   [(r["method"], r["path"]) for r in srv.requests])
        client.delete(f"/api/providers/{p['id']}")


# ---------------- 失败 / 超时 / 脱敏 ----------------

def test_hf_call_http_error_redacted(client, audio):
    with mock_gradio(fail_call=429, fail_message=f"Rate limit reached for {KEY}") as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "429" in done["error"] and "Rate limit" in done["error"]
        assert KEY not in done["error"] and "[REDACTED]" in done["error"]
        assert KEY not in (config.JOBS_DIR / j["id"] / "job.log").read_text()
        # 失败可重试
        assert client.post(f"/api/jobs/{j['id']}/retry").status_code == 200
        client.post(f"/api/jobs/{j['id']}/cancel")
        client.delete(f"/api/providers/{p['id']}")


def test_hf_sse_error_redacted(client, audio):
    with mock_gradio(sse_error=True, fail_message=f"GPU OOM for {KEY}") as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_hf_space(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "GPU OOM" in done["error"]
        assert KEY not in done["error"] and "[REDACTED]" in done["error"]
        client.delete(f"/api/providers/{p['id']}")


def test_hf_upload_error(client, audio):
    with mock_gradio(fail_upload=413) as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_hf_space(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "failed" and "413" in done["error"]
        # 上传失败 → 未 call
        assert all(r["path"] != "/gradio_api/call/generate_with_pe" or r["method"] != "POST"
                   for r in srv.requests)
        client.delete(f"/api/providers/{p['id']}")


def test_hf_timeout(client, audio, monkeypatch):
    monkeypatch.setattr(providers, "GRADIO_TIMEOUT_S", 0.6)
    with mock_gradio(hang=True, heartbeat_interval=0.02) as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        worker.run_hf_space(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "failed"
        assert "超时" in done["error"]
        client.delete(f"/api/providers/{p['id']}")


def test_hf_provider_deleted_fails(client, audio):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        client.delete(f"/api/providers/{p['id']}")
        worker.run_hf_space(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "failed" and "不存在" in done["error"]


def test_hf_wrong_kind_fails(client, audio):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        # 直接把 kind 改成 auk_remote → run_hf_space 拒绝
        db.connect().execute("UPDATE providers SET kind='auk_remote' WHERE id=?", (p["id"],))
        db.connect().commit()
        worker.run_hf_space(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "failed" and "kind" in done["error"]
        client.delete(f"/api/providers/{p['id']}")


# ---------------- 取消 ----------------

def test_hf_cancel_before_request(client, audio):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])
        db.update_job(j["id"], cancel_requested=1)
        worker.run_job(db.get_job(j["id"]), worker.EngineHolder())
        done = db.get_job(j["id"])
        assert done["status"] == "cancelled" and done["output_path"] is None
        assert len(srv.requests) == 0  # 未发出请求
        client.delete(f"/api/providers/{p['id']}")


def test_hf_cancel_during_sse(client, audio):
    with mock_gradio(heartbeats_before_done=1000, heartbeat_interval=0.02) as srv:
        p = _create_space(client, srv.base_url)
        j = _job(client, p["id"], "replace", audio["id"])

        def on_request(method, path, body):
            # SSE GET 到达时置取消标志
            if method == "GET" and path.startswith("/gradio_api/call/generate_with_pe/"):
                db.update_job(j["id"], cancel_requested=1)

        srv.on_request = on_request
        worker.run_hf_space(db.get_job(j["id"]))
        done = db.get_job(j["id"])
        assert done["status"] == "cancelled" and done["output_path"] is None
        client.delete(f"/api/providers/{p['id']}")


# ---------------- 代理配置解析（不触网） ----------------

def test_parse_proxy_url():
    cfg = providers.parse_proxy_url("socks5h://127.0.0.1:7897")
    assert cfg["host"] == "127.0.0.1" and cfg["port"] == 7897 and cfg["rdns"] is True
    assert cfg["type"] == socks.PROXY_TYPE_SOCKS5
    assert providers.parse_proxy_url("socks5://1.2.3.4:1080")["rdns"] is False
    assert providers.parse_proxy_url("socks4://h:1080")["type"] == socks.PROXY_TYPE_SOCKS4
    assert providers.parse_proxy_url("socks4a://h:1080")["rdns"] is True
    c = providers.parse_proxy_url("socks5h://user:pass@h:1080")
    assert c["username"] == "user" and c["password"] == "pass"


@pytest.mark.parametrize("url", ["", "http://h:8080", "socks5://", "socks5://host",
                                 "not-a-url", "socks5://h:99999", "ftp://h:21"])
def test_parse_proxy_url_invalid(url):
    with pytest.raises(ValueError):
        providers.parse_proxy_url(url)


def test_resolve_proxy_priority(monkeypatch):
    monkeypatch.delenv("HF_PROXY", raising=False)
    monkeypatch.delenv("AUK_SOCKS_PROXY", raising=False)
    assert providers.resolve_proxy() is None
    monkeypatch.setenv("AUK_SOCKS_PROXY", "socks5h://127.0.0.1:1080")
    assert providers.resolve_proxy()["port"] == 1080
    monkeypatch.setenv("HF_PROXY", "socks5h://127.0.0.1:2080")
    assert providers.resolve_proxy()["port"] == 2080  # HF_PROXY 优先
    monkeypatch.setenv("HF_PROXY", "bad-proxy")
    with pytest.raises(ValueError):
        providers.resolve_proxy()


def test_proxy_desc_no_creds():
    cfg = providers.parse_proxy_url("socks5h://user:pass@127.0.0.1:1080")
    d = providers.proxy_desc(cfg)
    assert "user" not in d and "pass" not in d and "127.0.0.1:1080" in d
    assert providers.proxy_desc(None) == "direct"


def test_remote_request_bad_proxy(monkeypatch):
    monkeypatch.setenv("HF_PROXY", "not-a-proxy")
    with pytest.raises(providers.ProviderError):
        providers.remote_request("https://x.example", "", "GET", "/api/health", timeout=1)


def test_proxy_engaged(monkeypatch):
    # 环回地址绕过代理（NO_PROXY 语义）：配置坏代理，本机 mock 仍直连可达
    with mock_gradio() as srv:
        monkeypatch.setenv("HF_PROXY", "socks5h://127.0.0.1:1")  # 端口 1：连接拒绝
        body, _ct, status = providers.remote_request(srv.base_url, "", "GET",
                                                     "/gradio_api/info", timeout=5)
        assert status == 200
    # 非环回地址走代理：坏代理必须失败（证明代理路径生效而非直连）
    with pytest.raises(providers.ProviderError):
        providers.remote_request("https://auk-studio-proxy-test.invalid", "", "GET",
                                 "/api/health", timeout=3)


# ---------------- test 端点（GET /gradio_api/info） ----------------

def test_test_endpoint_ok(client):
    with mock_gradio(required_key=KEY) as srv:
        p = _create_space(client, srv.base_url)
        r = client.post(f"/api/providers/{p['id']}/test")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["ok"] is True and isinstance(out["latency_ms"], int)
        assert KEY not in r.text
        req = srv.requests[0]
        assert req["method"] == "GET" and req["path"] == "/gradio_api/info"
        assert req["headers"].get("authorization") == f"Bearer {KEY}"
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_no_key(client):
    with mock_gradio() as srv:
        p = _create_space(client, srv.base_url, api_key="")
        assert client.post(f"/api/providers/{p['id']}/test").json()["ok"] is True
        assert "authorization" not in srv.requests[0]["headers"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_missing_endpoint(client):
    with mock_gradio(omit_endpoint=True) as srv:
        p = _create_space(client, srv.base_url)
        out = client.post(f"/api/providers/{p['id']}/test").json()
        assert out["ok"] is False and "run_generate_with_pe" in out["error"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_bad_key(client):
    with mock_gradio(required_key="hf-the-right-key-0000000000") as srv:
        p = _create_space(client, srv.base_url)  # 携带错误 key
        out = client.post(f"/api/providers/{p['id']}/test").json()
        assert out["ok"] is False and "401" in out["error"]
        assert KEY not in out["error"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_server_error(client):
    with mock_gradio(fail_info=500) as srv:
        p = _create_space(client, srv.base_url)
        out = client.post(f"/api/providers/{p['id']}/test").json()
        assert out["ok"] is False and "500" in out["error"]
        assert KEY not in out["error"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_unreachable(client):
    p = _create_space(client, "http://127.0.0.1:9")
    out = client.post(f"/api/providers/{p['id']}/test").json()
    assert out["ok"] is False and out["error"]
    client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_redirect_refused(client):
    with mock_gradio(redirect_to="http://169.254.169.254/latest") as srv:
        p = _create_space(client, srv.base_url)
        out = client.post(f"/api/providers/{p['id']}/test").json()
        assert out["ok"] is False and "重定向" in out["error"]
        client.delete(f"/api/providers/{p['id']}")