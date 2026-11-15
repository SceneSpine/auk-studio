"""远程 AuK provider：CRUD、key 掩码、base_url 校验（防 SSRF）、test 端点（/api/health）。

kind 仅 auk_remote（openai_tts 已移除）；model/voice 不使用（存空串、校验不要求）；
api_key 可选。不触外网：mock 绑定 127.0.0.1 随机端口；不加载本地模型。
"""
from __future__ import annotations

import pytest

from app.backend import providers

from mock_auk import mock_auk

KEY = "sk-test-secret-1234567890abcd"  # 尾 4 位 abcd
KEY2 = "sk-other-key-0987654321wxyz"  # 尾 4 位 wxyz


def _create(client, **kw) -> dict:
    payload = {
        "name": "Mock AuK", "kind": "auk_remote", "base_url": "https://auk.example.com",
        "api_key": KEY, **kw,
    }
    r = client.post("/api/providers", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- CRUD + key 掩码 ----------------

def test_create_and_masking(client):
    r = client.post("/api/providers", json={
        "name": "远程 AuK", "kind": "auk_remote", "base_url": "https://auk.example.com",
        "api_key": KEY,
    })
    assert r.status_code == 200, r.text
    p = r.json()
    assert KEY not in r.text  # 响应绝不出现完整 key
    assert p["has_key"] is True
    assert p["key_masked"] == "…abcd"
    assert p["enabled"] is True
    assert p["kind"] == "auk_remote"
    assert p["base_url"] == "https://auk.example.com"
    assert p["model"] == "" and p["voice"] == ""  # auk_remote 不使用 model/voice
    assert p["id"].startswith("prov_") and p["created_at"] > 0
    assert "api_key" not in p
    assert client.delete(f"/api/providers/{p['id']}").status_code == 200


def test_create_key_optional(client):
    p = _create(client, api_key="")
    assert p["has_key"] is False and p["key_masked"] == ""
    client.delete(f"/api/providers/{p['id']}")


def test_create_ignores_model_voice(client):
    # 提交 model/voice 被忽略，统一存空串
    p = _create(client, model="gpt-4o-mini-tts", voice="alloy")
    assert p["model"] == "" and p["voice"] == ""
    client.delete(f"/api/providers/{p['id']}")


def test_list_and_local_shape(client):
    p = _create(client)
    r = client.get("/api/providers")
    assert r.status_code == 200
    data = r.json()
    assert KEY not in r.text
    entry = next(x for x in data["providers"] if x["id"] == p["id"])
    assert entry["kind"] == "auk_remote"  # kind 透传
    # 测试环境无模型权重 → local.available=False；local 形状不变
    assert data["local"] == {"id": "local", "name": "本地 MLX", "available": False}
    client.delete(f"/api/providers/{p['id']}")


def test_update_and_delete(client):
    p = _create(client)
    r = client.put(f"/api/providers/{p['id']}", json={"name": "改名后的远程实例"})
    assert r.status_code == 200
    assert r.json()["name"] == "改名后的远程实例"
    assert KEY not in r.text
    r = client.delete(f"/api/providers/{p['id']}")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert all(x["id"] != p["id"] for x in client.get("/api/providers").json()["providers"])
    assert client.delete(f"/api/providers/{p['id']}").status_code == 404
    assert client.put(f"/api/providers/{p['id']}", json={"name": "x"}).status_code == 404
    assert client.post(f"/api/providers/{p['id']}/test").status_code == 404


# ---------------- base_url 校验（防 SSRF） ----------------

@pytest.mark.parametrize("url", [
    "http://192.168.1.10",
    "http://10.0.0.5:8080",
    "http://172.16.0.1",
    "http://169.254.169.254/latest",
    "http://evil.example.com",
    "http://localhost.evil.com",
    "http://127.0.0.1.nip.io",
    "ftp://auk.example.com",
    "not-a-url",
    "",
    "https://",
    "https://user:pass@auk.example.com",
    "https://auk.example.com?x=1",
])
def test_base_url_invalid_rejected(client, url):
    r = client.post("/api/providers", json={
        "name": "bad", "kind": "auk_remote", "base_url": url, "api_key": KEY,
    })
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "invalid_provider"


@pytest.mark.parametrize("url", [
    "https://auk.example.com",
    "https://my-space.hf.space",
    "http://127.0.0.1:7862",
    "http://localhost:8080",
])
def test_base_url_valid_accepted(client, url):
    p = _create(client, base_url=url)
    assert p["base_url"] == url
    client.delete(f"/api/providers/{p['id']}")


def test_base_url_trailing_slash_normalized(client):
    p = _create(client, base_url="https://auk.example.com/")
    assert p["base_url"] == "https://auk.example.com"
    client.delete(f"/api/providers/{p['id']}")


def test_validate_base_url_unit():
    assert providers.validate_base_url("https://x.example/") == "https://x.example"
    assert providers.validate_base_url("http://localhost:9") == "http://localhost:9"
    with pytest.raises(ValueError):
        providers.validate_base_url("http://192.168.0.1")
    with pytest.raises(ValueError):
        providers.validate_base_url("http://127.0.0.1:99999")  # 非法端口


# ---------------- 必填 / kind 校验 ----------------

@pytest.mark.parametrize("missing", ["name", "base_url"])
def test_create_missing_required(client, missing):
    payload = {"name": "x", "kind": "auk_remote", "base_url": "https://auk.example.com", "api_key": KEY}
    del payload[missing]
    assert client.post("/api/providers", json=payload).status_code == 422


def test_create_blank_name_and_bad_kind(client):
    r = client.post("/api/providers", json={
        "name": "   ", "kind": "auk_remote", "base_url": "https://auk.example.com",
    })
    assert r.status_code == 400
    for kind in ("openai_tts", "other_kind"):
        r = client.post("/api/providers", json={
            "name": "x", "kind": kind, "base_url": "https://auk.example.com",
        })
        assert r.status_code == 422, kind


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
    r = client.put(f"/api/providers/{p['id']}", json={"base_url": "http://10.0.0.1"})
    assert r.status_code == 400
    # 失败的 PUT 不影响原值
    cur = next(x for x in client.get("/api/providers").json()["providers"] if x["id"] == p["id"])
    assert cur["base_url"] == "https://auk.example.com"
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


# ---------------- test 端点（GET /api/health，本地 mock） ----------------

def test_test_endpoint_ok(client):
    with mock_auk(required_key=KEY) as srv:
        p = _create(client, base_url=srv.base_url)
        r = client.post(f"/api/providers/{p['id']}/test")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["ok"] is True
        assert isinstance(out["latency_ms"], int) and out["latency_ms"] >= 0
        assert KEY not in r.text
        assert len(srv.requests) == 1
        req = srv.requests[0]
        assert req["method"] == "GET" and req["path"] == "/api/health"
        assert req["headers"].get("authorization") == f"Bearer {KEY}"
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_no_key(client):
    with mock_auk() as srv:  # 不要求鉴权
        p = _create(client, base_url=srv.base_url, api_key="")
        assert p["has_key"] is False and p["key_masked"] == ""
        r = client.post(f"/api/providers/{p['id']}/test")
        assert r.json()["ok"] is True
        assert "authorization" not in srv.requests[0]["headers"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_bad_key(client):
    with mock_auk(required_key="sk-the-right-key-0000000000") as srv:
        p = _create(client, base_url=srv.base_url)  # 携带错误 key
        r = client.post(f"/api/providers/{p['id']}/test")
        out = r.json()
        assert out["ok"] is False
        assert "401" in out["error"]
        assert KEY not in out["error"]
        assert KEY not in r.text
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_server_error(client):
    with mock_auk(fail_health=500) as srv:
        p = _create(client, base_url=srv.base_url)
        out = client.post(f"/api/providers/{p['id']}/test").json()
        assert out["ok"] is False
        assert "500" in out["error"]
        assert KEY not in out["error"]
        client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_unreachable(client):
    p = _create(client, base_url="http://127.0.0.1:9")  # 端口 9：连接拒绝
    out = client.post(f"/api/providers/{p['id']}/test").json()
    assert out["ok"] is False
    assert out["error"]
    assert out["latency_ms"] is not None
    client.delete(f"/api/providers/{p['id']}")


def test_test_endpoint_redirect_refused(client):
    # 不跟随重定向（防 https → http 内网跳转的 SSRF 绕过）
    with mock_auk(redirect_to="http://169.254.169.254/latest") as srv:
        p = _create(client, base_url=srv.base_url)
        out = client.post(f"/api/providers/{p['id']}/test").json()
        assert out["ok"] is False
        assert "重定向" in out["error"]
        client.delete(f"/api/providers/{p['id']}")