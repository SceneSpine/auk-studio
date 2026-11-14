"""系统诊断与 preflight：结构、suggestion 强制、缓存、实测区间。"""
from __future__ import annotations


def test_diagnostics_structure(client):
    r = client.get("/api/system/diagnostics")
    assert r.status_code == 200
    j = r.json()
    assert j["platform"]["python"]
    assert j["platform"]["arch"]
    assert j["memory"]["total_gb"] > 0
    assert j["memory"]["pressure_label"] in ("正常", "偏高", "严重", "不可用")
    assert j["disk"]["total_gb"] > 0
    assert j["readiness"]["level"] in ("ready", "caution", "blocked", "unknown")
    assert j["overall"] == j["readiness"]["level"]
    ids = {c["id"] for c in j["checks"]}
    for required in ("arch", "macos", "metal", "mlx", "memory_pressure", "swap",
                     "disk_free", "ffmpeg", "git", "uv", "model_weights", "worker"):
        assert required in ids, f"缺少检查项 {required}"
    for c in j["checks"]:
        assert c["status"] in ("ok", "warn", "fail", "unknown")
        assert isinstance(c["measured"], bool)
        if c["status"] in ("warn", "fail"):
            assert c["suggestion"], f"{c['id']} 缺少 suggestion"


def test_diagnostics_cache_5s(client):
    a = client.get("/api/system/diagnostics").json()
    b = client.get("/api/system/diagnostics").json()
    assert a["generated_at"] == b["generated_at"]  # 5s 内命中缓存


def test_preflight_flash_8bit_baseline(client):
    r = client.post("/api/system/preflight", json={
        "model_variant": "flash", "task": "speech_edit", "bits": 8,
    })
    assert r.status_code == 200
    j = r.json()
    assert j["level"] in ("ready", "caution", "blocked", "unknown")
    assert isinstance(j["reasons"], list) and j["reasons"]
    assert j["estimates"]["rtf_range"] == [0.5, 1.0]
    assert j["estimates"]["peak_memory_gb"] == 7.6
    assert "非承诺" in j["estimates"]["note"]
    assert "本机实测" in j["estimates"]["note"]
    assert j["disk_free_gb"] > 0


def test_preflight_base_baseline(client):
    j = client.post("/api/system/preflight", json={
        "model_variant": "base", "task": "speech_edit", "bits": 8,
    }).json()
    assert j["estimates"]["rtf_range"] == [1.97, 2.21]


def test_preflight_no_baseline_null(client):
    j = client.post("/api/system/preflight", json={
        "model_variant": "base", "task": "speech_edit", "bits": 4,
    }).json()
    assert j["estimates"]["rtf_range"] is None
    assert j["estimates"]["peak_memory_gb"] is None


def test_preflight_not_supported_blocked(client):
    j = client.post("/api/system/preflight", json={
        "model_variant": "flash", "task": "speech_enhancement", "bits": 8,
    }).json()
    assert j["level"] == "blocked"
    assert any("不支持" in r for r in j["reasons"])


def test_preflight_accepts_mode_alias(client):
    j = client.post("/api/system/preflight", json={
        "model_variant": "flash", "task": "instruct_tts", "bits": 8,
    }).json()
    assert j["level"] in ("ready", "caution", "blocked", "unknown")


def test_preflight_invalid_variant(client):
    assert client.post("/api/system/preflight", json={"model_variant": "xxl"}).status_code == 422