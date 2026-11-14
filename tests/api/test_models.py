"""模型清单 / install-plan 复用 / 许可 403 / verify / activate。"""
from __future__ import annotations


def test_models_list_four_entries(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    j = r.json()
    ids = [m["id"] for m in j["models"]]
    assert ids == ["auk-flash", "auk-base", "qwen-thinker", "vae"]
    assert "active" in j and "worker" in j
    flash = j["models"][0]
    assert flash["role"] == "main"
    assert flash["license"]["commercial"] is True
    assert flash["depends_on"] == ["qwen-thinker", "vae"]
    qwen = j["models"][2]
    assert qwen["license"]["commercial"] is False
    assert qwen["role"] == "dependency"
    assert flash["memory_fit"] in ("comfortable", "tight", "insufficient", "unknown")


def test_models_not_installed_when_empty(client):
    j = client.get("/api/models").json()
    assert all(m["state"] == "not_installed" for m in j["models"])
    assert j["active"] is None


def test_models_ready_with_fake_weights(client, fake_weights):
    j = client.get("/api/models").json()
    assert all(m["state"] == "ready" for m in j["models"]), j
    assert all(m["downloaded"] and m["converted"] for m in j["models"])


def test_install_plan_already_ready_reuse(client, fake_weights):
    r = client.post("/api/models/auk-flash/install-plan")
    assert r.status_code == 200
    j = r.json()
    assert j["already_ready"] is True
    assert j["requires_consent"] is False
    assert j["total_download_gb"] == 0
    assert all(s["kind"] == "reuse" for s in j["steps"])


def test_install_plan_missing_weights(client):
    r = client.post("/api/models/auk-flash/install-plan")
    j = r.json()
    assert j["already_ready"] is False
    assert j["requires_consent"] is True
    kinds = [s["kind"] for s in j["steps"]]
    assert "download" in kinds and "verify" in kinds and "convert" in kinds and "quantize" in kinds
    assert j["total_download_gb"] > 6
    lic_ids = [l["id"] for l in j["licenses"]]
    assert "qwen-research" in lic_ids and "mit-auk" in lic_ids
    # 下载源 allowlist
    dl = next(s for s in j["steps"] if s["kind"] == "download")
    assert dl["source"] in ("Tencent-Hunyuan/AuK-Flash", "Tencent-Hunyuan/AuK", "Qwen/Qwen2.5-Omni-3B")


def test_install_plan_reuses_existing_raw(client, fake_weights):
    """有原始权重但缺转换产物 → download 步骤为 reuse，仅转换。"""
    from app.backend import config
    (config.MLX_DIR / "dit_flash.safetensors").unlink()
    try:
        j = client.post("/api/models/auk-flash/install-plan").json()
        assert j["already_ready"] is False
        assert j["total_download_gb"] == 0
        kinds = [s["kind"] for s in j["steps"]]
        assert "download" not in kinds
        assert "reuse" in kinds and "convert" in kinds
        m = next(m for m in client.get("/api/models").json()["models"] if m["id"] == "auk-flash")
        assert m["state"] == "not_installed"
        assert "复用" in (m["state_detail"] or "")
    finally:
        (config.MLX_DIR / "dit_flash.safetensors").write_bytes(b"fake-mlx")


def test_install_requires_license_consent(client):
    r = client.post("/api/models/auk-flash/install", json={"consent_license_ids": []})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "license_consent_required"
    # 只同意 MIT，缺 qwen → 仍 403
    r = client.post("/api/models/auk-flash/install", json={"consent_license_ids": ["mit-auk"]})
    assert r.status_code == 403
    assert "qwen-research" in r.json()["detail"]["details"]["missing"]


def test_install_creates_persistent_job(client):
    r = client.post("/api/models/auk-flash/install",
                    json={"consent_license_ids": ["mit-auk", "qwen-research"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["kind"] == "install"
    assert j["model_id"] == "auk-flash"
    assert j["status"] == "queued"
    assert j["install_json"]["phase"] == "prepare"
    # 重复安装 → 409
    r2 = client.post("/api/models/auk-flash/install",
                     json={"consent_license_ids": ["mit-auk", "qwen-research"]})
    assert r2.status_code == 409
    # kind 过滤可见，且列表/详情均含 model_id（前端关联依赖）
    lst = client.get("/api/jobs", params={"kind": "install"}).json()
    assert any(x["id"] == j["id"] and x["model_id"] == "auk-flash" for x in lst)
    detail = client.get(f"/api/jobs/{j['id']}").json()
    assert detail["model_id"] == "auk-flash"
    # 清理：排队中取消
    assert client.post(f"/api/jobs/{j['id']}/cancel").status_code == 200


def test_install_already_ready_409(client, fake_weights):
    r = client.post("/api/models/auk-flash/install",
                    json={"consent_license_ids": ["mit-auk", "qwen-research"]})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "model_already_ready"


def test_verify_creates_job(client, fake_weights):
    r = client.post("/api/models/qwen-thinker/verify")
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "verify"
    assert j["model_id"] == "qwen-thinker"
    client.post(f"/api/jobs/{j['id']}/cancel")


def test_activate(client, fake_weights):
    r = client.post("/api/models/auk-base/activate")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    from app.backend import db
    assert db.consume_activate_request() == "base"
    # 依赖组件不可激活
    assert client.post("/api/models/vae/activate").status_code == 400


def test_activate_not_ready_409(client):
    r = client.post("/api/models/auk-base/activate")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "model_not_ready"


def test_unknown_model_404(client):
    assert client.post("/api/models/nope/install-plan").status_code == 404
    assert client.post("/api/models/nope/install", json={"consent_license_ids": []}).status_code == 404
    assert client.post("/api/models/nope/verify").status_code == 404
    assert client.post("/api/models/nope/activate").status_code == 404