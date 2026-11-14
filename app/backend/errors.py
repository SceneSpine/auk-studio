"""统一错误结构 {code, message, details, trace_id}（docs/API_CONTRACT.md）。

旧端点保持字符串 detail 兼容；新端点用 api_error() 抛结构化 detail。
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, details=None) -> None:
    raise HTTPException(
        status_code,
        {"code": code, "message": message, "details": details, "trace_id": uuid.uuid4().hex[:12]},
    )