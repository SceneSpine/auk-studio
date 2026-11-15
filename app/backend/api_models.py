"""新端点：模型清单 / 安装计划 / 安装 / 校验 / 激活（docs/API_CONTRACT.md）。"""
from __future__ import annotations

from fastapi import APIRouter

from . import db, diagnostics, model_manager, schemas
from .errors import api_error

router = APIRouter(prefix="/api")


def _entry_or_404(model_id: str) -> dict:
    entry = model_manager.get_entry(model_id)
    if entry is None:
        api_error(404, "model_not_found", f"未知模型 {model_id}",
                  {"known": [m["id"] for m in model_manager.load_registry()["models"]]})
    return entry


def _worker_alive(ws: dict) -> bool:
    # 跨平台存活检查（Windows 上 os.kill(pid, 0) 会无条件杀进程，见 diagnostics.pid_alive）
    return diagnostics.pid_alive(ws.get("pid"))


@router.get("/models", response_model=schemas.ModelsResponse)
def models_list():
    registry = model_manager.load_registry()
    ws = db.get_worker_state() or {}
    ws = {**ws, "alive": _worker_alive(ws)}
    models = [model_manager.model_info(m, ws) for m in registry["models"]]
    active = next((m["id"] for m in models if m["active"]), None)
    return {"models": models, "active": active, "worker": ws}


@router.post("/models/{model_id}/install-plan", response_model=schemas.InstallPlan)
def install_plan(model_id: str):
    """无副作用：探测已存在文件，绝不重复下载。"""
    _entry_or_404(model_id)
    return model_manager.build_install_plan(model_id)


@router.post("/models/{model_id}/install")
def install_model(model_id: str, body: schemas.InstallBody):
    entry = _entry_or_404(model_id)
    plan = model_manager.build_install_plan(model_id)
    if plan["already_ready"]:
        api_error(409, "model_already_ready", f"{entry['display_name']} 已就绪，无需安装（复用现有权重）。")
    required = [lic["id"] for lic in plan["licenses"]]
    missing = [i for i in required if i not in (body.consent_license_ids or [])]
    if missing:
        api_error(403, "license_consent_required",
                  "安装前须同意相关许可（含 Qwen Research License 非商用限制）。",
                  {"required": required, "missing": missing,
                   "licenses": plan["licenses"]})
    if not plan["disk_ok"]:
        api_error(409, "insufficient_disk",
                  f"磁盘余量 {plan['disk_free_gb']}GB 不足（需约 {plan['extra_disk_gb']}GB，含转换临时空间）。",
                  {"disk_free_gb": plan["disk_free_gb"], "extra_disk_gb": plan["extra_disk_gb"]})
    active = db.active_model_job(model_id)
    if active:
        api_error(409, "install_in_progress", f"已有进行中的安装/校验任务 {active['id']}。",
                  {"job_id": active["id"]})
    job = db.insert_job({
        "audio_id": None, "mode": "install", "kind": "install", "model_id": model_id,
        "model_variant": entry.get("variant") or "flash",
        "instruction": f"安装 {entry['display_name']}",
        "note": "已同意许可：" + ", ".join(body.consent_license_ids or []),
    })
    db.update_job(job["id"], install_json=__import__("json").dumps(
        {"phase": "prepare", "downloaded_bytes": 0, "total_bytes": 0,
         "files_done": 0, "files_total": 0, "detail": "排队等待 worker 执行"}))
    return db.get_job(job["id"])


@router.post("/models/{model_id}/verify")
def verify_model(model_id: str):
    _entry_or_404(model_id)
    active = db.active_model_job(model_id)
    if active:
        api_error(409, "install_in_progress", f"已有进行中的安装/校验任务 {active['id']}。",
                  {"job_id": active["id"]})
    job = db.insert_job({
        "audio_id": None, "mode": "verify", "kind": "verify", "model_id": model_id,
        "model_variant": "flash",
        "instruction": f"校验 {model_id} 原始权重 sha256",
    })
    db.update_job(job["id"], install_json=__import__("json").dumps(
        {"phase": "verify", "files_done": 0, "files_total": 0, "detail": "排队等待 worker 执行"}))
    return db.get_job(job["id"])


@router.post("/models/{model_id}/activate")
def activate_model(model_id: str):
    entry = _entry_or_404(model_id)
    if entry.get("role") != "main" or not entry.get("variant"):
        api_error(400, "not_activatable", "依赖组件（Thinker/VAE）无需单独激活，随主模型加载。")
    st = model_manager.model_state(entry)
    if st["state"] != "ready":
        api_error(409, "model_not_ready", f"{entry['display_name']} 未就绪（{st['state']}），请先安装。",
                  {"state": st["state"], "state_detail": st["state_detail"]})
    db.request_activate(entry["variant"])
    return {"ok": True,
            "message": f"已请求切换，将在当前任务完成后加载 {entry['display_name']}（不强制卸载运行中模型）。"}