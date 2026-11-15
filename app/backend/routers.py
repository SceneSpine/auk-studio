"""AuK Studio API 路由（方案 §7）。所有文件访问限定在项目数据目录内。"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import audio, config, db

router = APIRouter(prefix="/api")

AUDIO_MIME = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".flac": "audio/flac", ".ogg": "audio/ogg", ".aac": "audio/aac",
    ".aiff": "audio/aiff", ".aif": "audio/aiff", ".mp4": "audio/mp4",
}


def _safe_data_path(p: str | Path) -> Path:
    rp = Path(p).resolve()
    if not rp.is_relative_to(config.DATA_DIR.resolve()):
        raise HTTPException(403, "路径越界")
    return rp


# ---------------- health / system ----------------

@router.get("/health")
def health():
    return {"status": "ok", "app": "AuK Studio", "time": time.time()}


def _worker_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@router.get("/system")
def system():
    disk = shutil.disk_usage(config.ROOT)
    ws = db.get_worker_state() or {}
    worker_alive = _worker_alive(ws.get("pid"))
    return {
        "platform": {
            "machine": platform.machine(),
            "system": platform.system(),
            "mac_ver": platform.mac_ver()[0],
            "processor": platform.processor(),
        },
        "memory": {
            "total_gb": round(int(subprocess.run(["sysctl", "-n", "hw.memsize"],
                                  capture_output=True, text=True).stdout.strip()) / 1e9, 1),
            "pressure_level": audio.memory_pressure_level(),
        },
        "disk": {"total_gb": round(disk.total / 1e9, 1), "free_gb": round(disk.free / 1e9, 1)},
        "worker": {**ws, "alive": worker_alive},
        "paths": {"data": str(config.DATA_DIR), "models": str(config.MODELS_DIR), "logs": str(config.LOGS_DIR)},
        "inference_backend": "MLX/Metal" if ws.get("metal_available") else "未确认",
    }


# ---------------- model ----------------

def _model_files_status() -> dict:
    checks = {
        "flash_dit": config.FLASH_DIR / "auk_flash.safetensors",
        "flash_vae": config.FLASH_DIR / "vae.safetensors",
        "flash_config": config.FLASH_DIR / "config.yaml",
        "qwen_shard_1": config.QWEN_DIR / "model-00001-of-00003.safetensors",
        "qwen_shard_2": config.QWEN_DIR / "model-00002-of-00003.safetensors",
        "qwen_shard_3": config.QWEN_DIR / "model-00003-of-00003.safetensors",
        "qwen_config": config.QWEN_DIR / "config.json",
        "mlx_vae": config.MLX_DIR / "vae.safetensors",
        "mlx_dit_flash": config.MLX_DIR / "dit_flash.safetensors",
        "mlx_fusion_flash": config.MLX_DIR / "fusion_flash.safetensors",
        "mlx_thinker": config.MLX_DIR / "thinker" / "thinker.safetensors",
        "mlx_dit_flash_q8": config.MLX_DIR / "dit_flash.q8.safetensors",
        "mlx_thinker_q8": config.MLX_DIR / "thinker" / "thinker.q8.safetensors",
        "base_dit": config.BASE_DIR / "auk_base.safetensors",
        "base_config": config.BASE_DIR / "config.yaml",
        "mlx_dit_base": config.MLX_DIR / "dit_base.safetensors",
        "mlx_fusion_base": config.MLX_DIR / "fusion_base.safetensors",
        "mlx_dit_base_q8": config.MLX_DIR / "dit_base.q8.safetensors",
    }
    return {k: {"exists": p.exists(), "size_gb": round(p.stat().st_size / 1e9, 3) if p.exists() else 0}
            for k, p in checks.items()}


@router.get("/model/status")
def model_status():
    files = _model_files_status()
    downloaded = all(files[k]["exists"] for k in
                     ("flash_dit", "flash_vae", "flash_config", "qwen_shard_1", "qwen_shard_2", "qwen_shard_3", "qwen_config"))
    converted = all(files[k]["exists"] for k in ("mlx_vae", "mlx_dit_flash", "mlx_fusion_flash", "mlx_thinker"))
    quantized = files["mlx_dit_flash_q8"]["exists"] and files["mlx_thinker_q8"]["exists"]
    base_ready = all(files[k]["exists"] for k in ("base_dit", "base_config", "mlx_dit_base", "mlx_fusion_base"))
    ws = db.get_worker_state() or {}
    ws["alive"] = _worker_alive(ws.get("pid"))
    return {
        "variant": "AuK-Flash",
        "downloaded": downloaded,
        "converted": converted,
        "quantized_q8": quantized,
        "base_ready": base_ready,
        "loaded": bool(ws.get("model_loaded")),
        "worker": ws,
        "files": files,
        "license_note": "Qwen2.5-Omni-3B 为 Qwen Research License（非商用）。详见 docs/MODEL_LICENSES.md",
    }


@router.post("/model/unload")
def model_unload():
    db.request_unload()
    return {"ok": True, "message": "已请求卸载；worker 将在当前任务结束后释放模型"}


# ---------------- audio ----------------

@router.post("/audio/upload")
async def upload_audio(file: UploadFile):
    name = file.filename or "audio"
    ext = Path(name).suffix.lower()
    if ext not in config.ALLOWED_EXT:
        raise HTTPException(400, f"不支持的格式 '{ext}'。支持: {', '.join(sorted(config.ALLOWED_EXT))}")
    aid = db.new_id("aud")
    stored = config.UPLOAD_DIR / f"{aid}{ext}"  # 随机 ID，不使用用户文件名作路径
    size = 0
    h = hashlib.sha256()
    with open(stored, "wb") as f:
        while chunk := await file.read(4 * 1024 * 1024):
            size += len(chunk)
            if size > config.MAX_UPLOAD_MB * 1024 * 1024:
                f.close()
                stored.unlink(missing_ok=True)
                raise HTTPException(413, f"文件超过 {config.MAX_UPLOAD_MB} MB 限制")
            h.update(chunk)
            f.write(chunk)
    try:
        meta = audio.probe(stored)
    except ValueError as e:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    if meta["duration"] > config.MAX_DURATION_S:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, f"时长 {meta['duration']:.1f}s 超过 {config.MAX_DURATION_S:.0f}s 限制")
    if meta["duration"] <= 0.2:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, "音频过短（<0.2s）")

    norm = config.UPLOAD_DIR / f"{aid}_24k.wav"
    try:
        audio.normalize(stored, norm)
    except Exception as e:  # noqa: BLE001
        stored.unlink(missing_ok=True)
        raise HTTPException(400, f"音频解码失败: {e}")
    peaks = audio.waveform_peaks(norm)
    (config.WAVEFORM_DIR / f"{aid}.json").write_text(json.dumps(peaks))

    rec = db.insert_audio({
        "id": aid, "original_name": name, "stored_path": str(stored), "normalized_path": str(norm),
        "format": meta["format"], "sample_rate": meta["sample_rate"], "channels": meta["channels"],
        "bit_depth": meta["bit_depth"], "duration": meta["duration"], "size_bytes": size,
        "sha256": h.hexdigest(),
    })
    db.register_file(stored, "upload", audio_id=aid, label=name)
    return {**rec, "waveform": peaks}


@router.get("/audio")
def audio_list():
    return db.list_audio()


@router.get("/audio/{audio_id}")
def audio_get(audio_id: str):
    a = db.get_audio(audio_id)
    if not a:
        raise HTTPException(404, "音频不存在")
    return a


@router.get("/audio/{audio_id}/waveform")
def audio_waveform(audio_id: str):
    a = db.get_audio(audio_id)
    if not a:
        raise HTTPException(404, "音频不存在")
    cache = config.WAVEFORM_DIR / f"{audio_id}.json"
    if cache.exists():
        return JSONResponse(json.loads(cache.read_text()))
    peaks = audio.waveform_peaks(a["normalized_path"] or a["stored_path"])
    cache.write_text(json.dumps(peaks))
    return peaks


@router.get("/audio/{audio_id}/stream")
def audio_stream(audio_id: str, request: Request):
    a = db.get_audio(audio_id)
    if not a:
        raise HTTPException(404, "音频不存在")
    return _range_file(Path(a["stored_path"]), AUDIO_MIME.get(Path(a["stored_path"]).suffix.lower(), "application/octet-stream"), request)


def _range_file(path: Path, mime: str, request: Request) -> Response:
    """支持 Range 的音频流（浏览器 seeks 需要）。"""
    if not path.exists():
        raise HTTPException(404, "文件缺失")
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if range_header:
        try:
            units, rng = range_header.split("=", 1)
            start_s, end_s = rng.split("-", 1)
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                raise ValueError
        except ValueError:
            raise HTTPException(416, "无效 Range")
        length = end - start + 1

        def iterfile():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(1024 * 512, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(iterfile(), status_code=206, media_type=mime, headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        })
    return FileResponse(path, media_type=mime, headers={"Accept-Ranges": "bytes"})


@router.delete("/audio/{audio_id}")
def audio_delete(audio_id: str, force: bool = False):
    a = db.get_audio(audio_id)
    if not a:
        raise HTTPException(404, "音频不存在")
    refs = db.rows(db.connect().execute("SELECT id FROM jobs WHERE audio_id=?", (audio_id,)))
    file_refs = db.rows(db.connect().execute("SELECT id FROM files WHERE audio_id=? AND kind!='upload'", (audio_id,)))
    if (refs or file_refs) and not force:
        raise HTTPException(409, f"有 {len(refs)} 个任务、{len(file_refs)} 个结果文件引用此音频；请先删除相关任务或使用 force=true")
    for p in (a["stored_path"], a["normalized_path"]):
        if p:
            Path(p).unlink(missing_ok=True)
    (config.WAVEFORM_DIR / f"{audio_id}.json").unlink(missing_ok=True)
    db.delete_audio(audio_id)
    return {"ok": True}


# ---------------- jobs ----------------

class JobCreate(BaseModel):
    audio_id: str | None = None
    mode: str = Field("replace", pattern="^(replace|full|custom|tts|instruct_tts|timbre|emotion)$")
    original_text: str = ""
    target_text: str = ""
    segment: dict = Field(default_factory=dict)
    instruction: str = ""
    model_variant: str = Field("flash", pattern="^(flash|base)$")
    bits: int | None = Field(None, description="None=fp32, 8 推荐, 4 官方不建议（中文退化）")
    sequential: bool = False
    seed: int | None = None
    gen_seconds: float | None = Field(None, gt=0.2, le=300)
    nfe: int | None = Field(None, ge=4, le=64, description="ODE 步数，仅 base 生效，默认 32")
    kind: str = Field("infer", pattern="^(infer|install|verify)$")
    voice_id: str | None = None
    description: str = ""
    emotion: str = ""
    provider_id: str | None = Field(None, description="null/'local'=本地 MLX；auk_remote 支持全部 7 模式")


EMOTIONS = ("开心", "愤怒", "悲伤", "恐惧", "惊讶", "厌恶", "平静", "兴奋")


@router.post("/jobs")
def create_job(body: JobCreate):
    from . import capabilities, voices
    from .errors import api_error

    if body.kind != "infer":
        api_error(400, "invalid_kind", "install/verify 任务请通过 /api/models/{id}/install 或 /verify 创建。")

    # ---- provider 分支：auk_remote 全 7 模式放行（能力以远程实际为准，不走本地能力门禁） ----
    provider_id = (body.provider_id or "").strip() or None
    if provider_id == "local":
        provider_id = None
    p = None
    if provider_id:
        from . import providers

        p = providers.get_raw(provider_id)
        if not p:
            api_error(400, "provider_not_found", "Provider 不存在", {"provider_id": provider_id})
        if not p["enabled"]:
            api_error(409, "provider_disabled", f"Provider「{p['name']}」已停用，请先启用",
                      {"provider_id": provider_id})

    if body.bits not in (None, 4, 8):
        raise HTTPException(400, "bits 仅支持 None(fp32)/4/8")

    if p:
        host = urlparse(p["base_url"]).hostname or ""
        note = f"远程 AuK：音频+文本将发送至 {host}（用户显式选择）"
    else:
        # 能力门禁（config/capabilities.json 实测判定）——仅本地
        allowed, note, _entry = capabilities.gate_mode(body.mode)
        if not allowed:
            api_error(400, "capability_not_supported", f"能力门禁：{body.mode} 不支持。{_entry.get('note', '')}",
                      {"mode": body.mode, "state": _entry.get("state")})

    audio_id = body.audio_id
    # 音色引用校验（任何带 voice_id 的任务）
    if body.voice_id:
        v = voices.get(body.voice_id)
        if not v:
            api_error(404, "voice_not_found", "音色不存在", {"voice_id": body.voice_id})
        if v["archived"]:
            api_error(400, "voice_archived", "音色已归档，不能用于新任务", {"voice_id": body.voice_id})

    if body.mode == "instruct_tts":
        # 无参考音频：description + target_text
        if not body.description.strip():
            raise HTTPException(400, "指令 TTS 需要 description（声音描述）")
        if not body.target_text.strip():
            raise HTTPException(400, "指令 TTS 需要 target_text")
        audio_id = None
    elif body.mode == "tts":
        if not body.target_text.strip():
            raise HTTPException(400, "零样本 TTS 需要 target_text")
        if not audio_id and body.voice_id:
            ref = voices.resolve_audio(body.voice_id)
            if not ref:
                api_error(400, "voice_audio_missing", "音色关联音频缺失，无法作为参考")
            audio_id = ref["id"]
        if not audio_id:
            raise HTTPException(400, "零样本 TTS 需要参考音频（audio_id 或 voice_id）")
    elif body.mode == "timbre":
        if not audio_id:
            raise HTTPException(400, "音色重塑需要 audio_id")
        if not body.description.strip():
            raise HTTPException(400, "音色重塑需要 description（目标音色描述）")
    elif body.mode == "emotion":
        if not audio_id:
            raise HTTPException(400, "情绪编辑需要 audio_id")
        if body.emotion not in EMOTIONS:
            raise HTTPException(400, f"emotion 仅支持：{'/'.join(EMOTIONS)}")
    else:
        if not audio_id:
            raise HTTPException(400, "该模式需要 audio_id")
        if body.mode == "replace":
            seg = body.segment or {}
            if not (seg.get("original") or "").strip() or not (seg.get("replacement") or "").strip():
                raise HTTPException(400, "局部替换需要 segment.original 与 segment.replacement")
        if body.mode == "full" and not body.target_text.strip():
            raise HTTPException(400, "全文替换需要 target_text")
        if body.mode == "custom" and not body.instruction.strip():
            raise HTTPException(400, "自定义模式需要 instruction")

    if audio_id and not db.get_audio(audio_id):
        raise HTTPException(404, "音频不存在")

    job = db.insert_job({
        "audio_id": audio_id, "mode": body.mode,
        "original_text": body.original_text, "target_text": body.target_text,
        "segment_json": body.segment, "instruction": body.instruction,
        "model_variant": body.model_variant, "bits": body.bits, "sequential": int(body.sequential),
        "seed": body.seed, "gen_seconds": body.gen_seconds, "nfe": body.nfe,
        "kind": "infer", "voice_id": body.voice_id,
        "description": body.description, "emotion": body.emotion, "note": note,
        "provider_id": provider_id,
    })
    return db.get_job(job["id"])


@router.get("/jobs")
def jobs_list(status: str | None = None, limit: int = 200, kind: str | None = None):
    return db.list_jobs(limit=min(limit, 1000), status=status, kind=kind)


@router.get("/jobs/{job_id}")
def job_get(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    j["audio"] = db.get_audio(j["audio_id"])
    j["files"] = db.rows(db.connect().execute("SELECT * FROM files WHERE job_id=? ORDER BY created_at", (job_id,)))
    return j


@router.get("/jobs/{job_id}/logs")
def job_logs(job_id: str, tail: int = 300):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    p = config.JOBS_DIR / job_id / "job.log"
    if not p.exists():
        return {"lines": [], "error": j.get("error", "")}
    lines = p.read_text(errors="replace").splitlines()
    return {"lines": lines[-tail:], "error": j.get("error", "")}


@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    if j["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(409, f"任务已处于终态 {j['status']}")
    if j["status"] == "queued":
        db.update_job(job_id, status="cancelled", cancel_requested=1, finished_at=time.time(), stage_detail="排队时取消")
        return {"ok": True, "state": "cancelled"}
    db.update_job(job_id, cancel_requested=1)
    return {"ok": True, "state": "stop_requested", "message": "正在请求停止：推理无法安全中断，将在当前阶段结束后停止"}


@router.post("/jobs/{job_id}/retry")
def job_retry(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    if j["status"] not in ("failed", "cancelled"):
        raise HTTPException(409, "仅失败/已取消的任务可重试")
    db.update_job(job_id, status="queued", error="", cancel_requested=0, stage_detail="重新排队",
                  started_at=None, finished_at=None, elapsed_s=None, output_path=None,
                  output_duration=None, peak_memory_gb=None, rtf=None)
    return db.get_job(job_id)


@router.delete("/jobs/{job_id}")
def job_delete(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    if j["status"] in ("preparing", "loading_model", "processing", "postprocessing"):
        raise HTTPException(409, "运行中的任务不能删除，请先取消")
    for f in db.rows(db.connect().execute("SELECT * FROM files WHERE job_id=?", (job_id,))):
        Path(f["path"]).unlink(missing_ok=True)
        db.connect().execute("DELETE FROM files WHERE id=?", (f["id"],))
    shutil.rmtree(config.JOBS_DIR / job_id, ignore_errors=True)
    with db.tx() as conn:
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return {"ok": True}


class AcceptBody(BaseModel):
    accepted: bool | None = None


@router.post("/jobs/{job_id}/accept")
def job_accept(job_id: str, body: AcceptBody):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    db.update_job(job_id, accepted=None if body.accepted is None else int(body.accepted))
    return {"ok": True}


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    files = db.rows(db.connect().execute("SELECT * FROM files WHERE job_id=? ORDER BY created_at", (job_id,)))
    for f in files:
        f["url"] = f"/api/files/{f['id']}"
        p = Path(f["path"])
        f["exists"] = p.exists()
        if p.exists() and p.suffix == ".wav":
            try:
                info = audio.probe(p)
                f["duration"] = info["duration"]
                f["sample_rate"] = info["sample_rate"]
            except Exception:  # noqa: BLE001
                pass
    return {"job": j, "files": files, "audio": db.get_audio(j["audio_id"])}


class SpliceBody(BaseModel):
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    cand_start_s: float = Field(0, ge=0)
    cand_end_s: float | None = None
    crossfade_ms: int = Field(30, ge=0, le=2000)


@router.post("/jobs/{job_id}/splice")
def job_splice(job_id: str, body: SpliceBody):
    """把候选（或其片段）拼回原始音频；未修改区域保留原始 PCM。"""
    j = db.get_job(job_id)
    if not j or not j.get("output_path"):
        raise HTTPException(404, "任务或候选音频不存在")
    a = db.get_audio(j["audio_id"])
    if not a:
        raise HTTPException(404, "原始音频不存在")
    if body.end_s <= body.start_s:
        raise HTTPException(400, "end_s 必须大于 start_s")
    out = config.OUTPUT_DIR / f"{job_id}_spliced_{db.new_id('x')[2:]}.wav"
    try:
        meta = audio.splice(
            a["stored_path"], j["output_path"], out,
            start_s=body.start_s, end_s=body.end_s,
            cand_start_s=body.cand_start_s, cand_end_s=body.cand_end_s,
            crossfade_ms=body.crossfade_ms,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"拼接失败: {e}")
    fid = db.register_file(out, "spliced", job_id=job_id, audio_id=a["id"], label="拼接完整音频")
    return {"file_id": fid, "url": f"/api/files/{fid}", **meta}


class TrimBody(BaseModel):
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)


@router.post("/jobs/{job_id}/trim")
def job_trim(job_id: str, body: TrimBody):
    """导出候选中的修改片段。"""
    j = db.get_job(job_id)
    if not j or not j.get("output_path"):
        raise HTTPException(404, "任务或候选音频不存在")
    if body.end_s <= body.start_s:
        raise HTTPException(400, "end_s 必须大于 start_s")
    out = config.OUTPUT_DIR / f"{job_id}_segment_{db.new_id('x')[2:]}.wav"
    try:
        meta = audio.trim(j["output_path"], out, body.start_s, body.end_s)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"片段导出失败: {e}")
    fid = db.register_file(out, "segment", job_id=job_id, audio_id=j["audio_id"], label="修改片段")
    return {"file_id": fid, "url": f"/api/files/{fid}", **meta}


# ---------------- files / settings ----------------

@router.get("/files/{file_id}")
def file_download(file_id: str, request: Request):
    f = db.get_file(file_id)
    if not f:
        raise HTTPException(404, "文件不存在")
    p = _safe_data_path(f["path"])
    if not p.exists():
        raise HTTPException(404, "文件已缺失")
    mime = AUDIO_MIME.get(p.suffix.lower(), "application/octet-stream")
    if request.query_params.get("download") == "1":
        # 下载文件名 = 安全化标签 + 真实扩展名（标签本身不含后缀，必须补上）
        label = f["label"] or p.stem
        safe = "".join(c for c in label if c.isalnum() or c in "._- ")[:80].strip() or p.stem
        if p.suffix and not safe.lower().endswith(p.suffix.lower()):
            safe += p.suffix
        return FileResponse(p, media_type=mime, filename=safe)
    return _range_file(p, mime, request)


@router.get("/settings")
def settings_get():
    return db.get_settings()


@router.put("/settings")
def settings_put(values: dict):
    allowed = {"theme", "crossfade_ms", "default_bits", "default_sequential", "idle_unload_s",
               "language", "allow_update_check", "default_variant"}
    clean = {k: v for k, v in values.items() if k in allowed}
    if "default_variant" in clean and clean["default_variant"] not in ("flash", "base"):
        raise HTTPException(400, "default_variant 仅支持 flash/base")
    return db.set_settings(clean)