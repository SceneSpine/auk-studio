"""新端点：在线 TTS provider CRUD + 连通性测试（docs/API_CONTRACT.md §Provider 扩展 v0.3）。

响应绝不包含完整 api_key（仅 has_key + key_masked）。
"""
from __future__ import annotations

from fastapi import APIRouter

from . import model_manager, providers, schemas
from .errors import api_error

router = APIRouter(prefix="/api")


def _local_available() -> bool:
    """本地 MLX 是否可用：任一主模型（role=main）处于 ready。"""
    try:
        for entry in model_manager.load_registry()["models"]:
            if entry.get("role") == "main" and model_manager.model_state(entry)["state"] == "ready":
                return True
    except Exception:  # noqa: BLE001 registry/manifest 缺失或探测失败 → 保守 false
        return False
    return False


@router.get("/providers", response_model=schemas.ProvidersResponse)
def providers_list():
    return {
        "providers": providers.list_providers(),
        "local": {"id": "local", "name": "本地 MLX", "available": _local_available()},
    }


@router.post("/providers", response_model=schemas.Provider)
def provider_create(body: schemas.ProviderCreate):
    try:
        return providers.create(body.model_dump())
    except ValueError as e:
        api_error(400, "invalid_provider", str(e))


@router.put("/providers/{provider_id}", response_model=schemas.Provider)
def provider_update(provider_id: str, body: schemas.ProviderUpdate):
    if not providers.get_raw(provider_id):
        api_error(404, "provider_not_found", "Provider 不存在", {"provider_id": provider_id})
    try:
        # exclude_unset：未提交的字段不修改；api_key 空串/None = 不修改（providers.update 语义）
        return providers.update(provider_id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        api_error(400, "invalid_provider", str(e))


@router.delete("/providers/{provider_id}")
def provider_delete(provider_id: str):
    if not providers.delete(provider_id):
        api_error(404, "provider_not_found", "Provider 不存在", {"provider_id": provider_id})
    return {"ok": True}


@router.post("/providers/{provider_id}/test", response_model=schemas.ProviderTestResult)
def provider_test(provider_id: str):
    result = providers.test_provider(provider_id)
    if result is None:
        api_error(404, "provider_not_found", "Provider 不存在", {"provider_id": provider_id})
    return result