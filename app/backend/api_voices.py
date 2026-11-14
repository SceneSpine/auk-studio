"""新端点：音色库 CRUD + 输出评分/下载（docs/API_CONTRACT.md）。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from . import db, schemas, voices
from .errors import api_error

router = APIRouter(prefix="/api")


# ---------------- voices ----------------

@router.get("/voices", response_model=list[schemas.Voice])
def voices_list(include_archived: bool = False):
    return voices.list_voices(include_archived)


@router.post("/voices", response_model=schemas.Voice)
def voice_create(body: schemas.VoiceCreate):
    if body.consent_confirmed is not True:
        api_error(403, "voice_consent_required",
                  "必须确认参考声音合法使用权（consent_confirmed=true）。",
                  {"statement": voices.CONSENT_STATEMENT})
    if not body.name.strip():
        api_error(400, "invalid_name", "音色名称不能为空")
    if not db.get_audio(body.audio_id):
        api_error(404, "audio_not_found", "关联音频不存在", {"audio_id": body.audio_id})
    if body.job_id and not db.get_job(body.job_id):
        api_error(404, "job_not_found", "关联任务不存在", {"job_id": body.job_id})
    return voices.create(body.model_dump())


@router.delete("/voices/{voice_id}")
def voice_delete(voice_id: str):
    if not voices.get(voice_id):
        api_error(404, "voice_not_found", "音色不存在")
    voices.delete(voice_id)
    return {"ok": True, "message": "音色记录已删除；关联音频文件保留（可能被任务引用）。"}


@router.post("/voices/{voice_id}/archive", response_model=schemas.Voice)
def voice_archive(voice_id: str, body: schemas.VoiceArchive):
    if not voices.get(voice_id):
        api_error(404, "voice_not_found", "音色不存在")
    return voices.set_archived(voice_id, body.archived)


# ---------------- outputs ----------------

@router.post("/outputs/{file_id}/rate")
def output_rate(file_id: str, body: schemas.RateBody):
    if body.rating is not None and not (1 <= body.rating <= 5):
        api_error(400, "invalid_rating", "rating 仅支持 1–5 或 null", {"rating": body.rating})
    if body.rating is None and body.favorite is None:
        api_error(400, "empty_rate", "至少提供 rating 或 favorite 之一")
    f = db.rate_file(file_id, body.rating, body.favorite)
    if not f:
        api_error(404, "file_not_found", "文件不存在")
    return f


@router.get("/outputs/{file_id}")
def output_get(file_id: str, request: Request):
    """等同 /api/files/{id}（安全下载/流式）。"""
    from .routers import file_download
    return file_download(file_id, request)