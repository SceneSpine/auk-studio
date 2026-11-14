"""新端点：capabilities / system diagnostics / preflight（docs/API_CONTRACT.md）。"""
from __future__ import annotations

from fastapi import APIRouter

from . import capabilities, diagnostics, schemas
from .errors import api_error

router = APIRouter(prefix="/api")


@router.get("/capabilities", response_model=schemas.Capabilities)
def get_capabilities():
    """直接读 config/capabilities.json（实测门禁）；缺失时保守默认。"""
    return capabilities.load_capabilities()


@router.get("/system/diagnostics", response_model=schemas.Diagnostics)
def system_diagnostics():
    """真实探针（sysctl/vm_stat/df/du/版本探测），5s 缓存；measured 区分观测/估计。"""
    return diagnostics.collect()


@router.post("/system/preflight", response_model=schemas.Preflight)
def system_preflight(body: schemas.PreflightBody):
    if body.bits not in (None, 4, 8):
        api_error(400, "invalid_bits", "bits 仅支持 None(fp32)/4/8")
    return diagnostics.preflight(body.model_variant, body.task, body.bits, body.sequential)