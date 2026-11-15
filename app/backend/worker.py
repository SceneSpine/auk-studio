"""AuK 推理 worker：独立进程，单任务串行。

- 从 SQLite 领取 queued 任务，调用官方 auk_mlx Python API（常驻引擎，跨任务复用）。
- 状态机：queued → preparing → loading_model → processing → postprocessing → completed/failed/cancelled。
- 取消：排队任务立即取消；运行中推理不可安全中断时，置 cancel_requested，
  在阶段边界停止（界面显示"正在请求停止"）。
- 模型管理：首个任务懒加载；空闲超时自动卸载；响应 unload 控制标志。
- 心跳写入 worker_state，供后端 /api/system 与看门狗使用。

以 `python -m app.backend.worker` 从项目根目录启动（由后端 supervisor 拉起）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import resource
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse

# 离线加载 HF processor，避免网络阻塞
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from . import audio, config, db, model_manager, providers, voices  # noqa: E402

log = logging.getLogger("auk.worker")


def _setup_logging() -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(config.LOGS_DIR / "worker.log")],
    )


def build_instruction(job: dict) -> str:
    """按官方 Cookbook 模板构造编辑指令，再附加用户的风格指令。

    本机实测结论（见 TEST_REPORT.md §3）：
    - 局部替换用内容编辑模板 把'X'改成'Y'（词级最可靠）。
    - 全文替换用零样本 TTS 英文模板 "Say the following with the same voice: '...'"，
      整句跟随显著优于中文内容编辑模板（Flash/Base 均验证成功）。
    - 保持类指令过多会抑制编辑，UI 默认仅音色+情绪。
    """
    mode = job.get("mode") or "replace"
    extra = (job.get("instruction") or "").strip()
    if mode == "custom":
        base = extra
    elif mode in ("full", "tts"):
        tgt = (job.get("target_text") or "").strip()
        if not tgt:
            raise ValueError("全文替换/零样本 TTS 模式必须填写目标文本")
        base = f"Say the following with the same voice: '{tgt}'"
    elif mode == "instruct_tts":
        desc = (job.get("description") or "").strip()
        tgt = (job.get("target_text") or "").strip()
        if not desc or not tgt:
            raise ValueError("指令 TTS 必须填写声音描述（description）与目标文本（target_text）")
        base = f'Based on the following description: "{desc}", generate speech content "{tgt}".'
    elif mode == "timbre":
        desc = (job.get("description") or "").strip()
        if not desc:
            raise ValueError("音色重塑必须填写目标音色描述（description）")
        base = f'请将这段音频的音色修改为符合以下描述的声音：“{desc}”。'
    elif mode == "emotion":
        emo = (job.get("emotion") or "").strip()
        if not emo:
            raise ValueError("情绪编辑必须填写目标情绪（emotion）")
        base = f'将情感转变为{emo}。'
    else:  # replace（局部片段）
        seg = job.get("segment") or {}
        orig = (seg.get("original") or "").strip()
        rep = (seg.get("replacement") or "").strip()
        if not orig or not rep:
            raise ValueError("局部替换必须填写原文片段和替换内容")
        base = f"把‘{orig}’改成‘{rep}’。"
    # TTS 英文模板（full/tts/instruct_tts）后不附加中文风格指令：
    # 实测模型会把模板后的中文指令当作台词读出来（TEST_REPORT §3.4）。
    # timbre/emotion 严格按实测选定模板，不附加额外指令。
    if mode == "replace" and extra:
        base = f"{base} {extra}"
    if not base:
        raise ValueError("编辑指令为空")
    return base


class EngineHolder:
    """常驻引擎管理：懒加载、参数变更重载、卸载释放。支持 flash / base 两个变体。"""

    def __init__(self) -> None:
        self.engine = None
        self.key: tuple | None = None
        self.load_seconds: float | None = None

    def ensure(self, variant: str, bits: int | None, sequential: bool):
        key = (variant, bits, sequential)
        if self.engine is not None and self.key == key:
            return self.engine
        self.unload()
        import mlx.core as mx

        from auk_mlx.infer import AukMLX

        model_dir = config.FLASH_DIR if variant == "flash" else config.BASE_DIR
        cfg_path = model_dir / "config.yaml"
        required = [
            cfg_path,
            config.MLX_DIR / "vae.safetensors",
            config.MLX_DIR / f"dit_{variant}.safetensors",
            config.MLX_DIR / f"fusion_{variant}.safetensors",
            config.MLX_DIR / "thinker" / "thinker.safetensors",
            config.QWEN_DIR / "config.json",
        ]
        missing = [str(p) for p in required if not Path(p).exists()]
        if missing:
            raise FileNotFoundError("模型文件缺失（请先下载并转换）: " + ", ".join(missing))
        t0 = time.time()
        log.info("加载引擎 variant=%s bits=%s sequential=%s device=%s metal=%s",
                 variant, bits, sequential, mx.default_device(), mx.metal.is_available())
        self.engine = AukMLX(
            str(config.MLX_DIR), str(cfg_path), str(config.QWEN_DIR),
            bits=bits, group_size=64, sequential=sequential,
        )
        self.key = key
        self.load_seconds = time.time() - t0
        log.info("引擎加载完成，耗时 %.1fs", self.load_seconds)
        return self.engine

    def unload(self) -> None:
        if self.engine is None:
            return
        import gc

        import mlx.core as mx

        self.engine.vae = self.engine.dit = self.engine.thinker = None
        self.engine = None
        self.key = None
        gc.collect()
        mx.clear_cache()
        log.info("模型已卸载，内存已释放")

    @property
    def loaded(self) -> bool:
        return self.engine is not None


def _peak_rss_gb() -> float:
    # macOS: ru_maxrss 单位为 bytes
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def _job_context(jid: str):
    """任务日志/阶段/取消 脚手架（推理与安装/校验任务共用）。"""
    job_dir = config.JOBS_DIR / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    jlog = logging.getLogger(f"job.{jid}")
    jlog.setLevel(logging.INFO)
    fh = logging.FileHandler(job_dir / "job.log")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    jlog.addHandler(fh)

    def stage(status: str, detail: str) -> None:
        db.update_job(jid, status=status, stage_detail=detail)
        db.worker_heartbeat(os.getpid(), current_job_id=jid)
        jlog.info("[%s] %s", status, detail)

    def cancelled() -> bool:
        j = db.get_job(jid)
        return bool(j and j["cancel_requested"])

    return jlog, fh, stage, cancelled


class _InstallCtx:
    """安装/校验任务回调：日志、阶段、install_json 进度（节流 1s）、取消。"""

    def __init__(self, jid: str, jlog, stage, cancelled):
        self.jid = jid
        self.jlog = jlog
        self.stage = stage
        self.cancelled = cancelled
        self._last_write = 0.0
        self._last_phase = ""

    def log(self, msg: str) -> None:
        self.jlog.info("%s", msg)

    def progress(self, phase, downloaded_bytes, total_bytes, files_done, files_total, detail) -> None:
        now = time.time()
        if phase == self._last_phase and now - self._last_write < 1.0 and phase != "done":
            return
        self._last_write = now
        self._last_phase = phase
        payload = {"phase": phase}
        if downloaded_bytes is not None:
            payload["downloaded_bytes"] = int(downloaded_bytes)
        if total_bytes is not None:
            payload["total_bytes"] = int(total_bytes)
        if files_done is not None:
            payload["files_done"] = int(files_done)
        if files_total is not None:
            payload["files_total"] = int(files_total)
        if detail:
            payload["detail"] = str(detail)[:1500]
        db.update_job(self.jid, install_json=json.dumps(payload, ensure_ascii=False),
                      stage_detail=(detail or phase)[:300])


def _run_model_job(job: dict, runner) -> None:
    """kind=install/verify 任务包装：与推理共用队列/日志/取消/重试，串行执行。"""
    jid = job["id"]
    jlog, fh, stage, cancelled = _job_context(jid)
    ctx = _InstallCtx(jid, jlog, stage, cancelled)
    t_start = time.time()
    try:
        runner(job, ctx)
        db.update_job(jid, status="completed", stage_detail="完成",
                      finished_at=time.time(), elapsed_s=time.time() - t_start)
        jlog.info("任务完成，耗时 %.1fs", time.time() - t_start)
    except model_manager.Cancelled as e:
        jlog.warning("任务取消: %s", e)
        db.update_job(jid, status="cancelled", error=str(e)[:2000],
                      finished_at=time.time(), elapsed_s=time.time() - t_start,
                      stage_detail="已取消（重试可断点续传）")
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        jlog.error("任务失败: %s\n%s", err, traceback.format_exc())
        db.update_job(jid, status="failed", error=err[:2000],
                      finished_at=time.time(), elapsed_s=time.time() - t_start, stage_detail="失败")
    finally:
        jlog.removeHandler(fh)
        fh.close()
        db.worker_heartbeat(os.getpid(), current_job_id=None)


def _candidate_ext(body: bytes, content_type: str) -> str:
    """按响应 Content-Type 决定候选扩展名（wav/mp3）；未知类型嗅探魔数，兜底 wav。"""
    ct = (content_type or "").lower()
    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "wav" in ct:
        return ".wav"
    if body[:3] == b"ID3" or body[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    return ".wav"


def run_online_tts(job: dict) -> None:
    """在线 TTS 任务（v0.3）：POST provider /audio/speech。

    - 不加载本地模型、不走内存护栏；与本地任务仍串行（单 worker）。
    - 取消：请求前检查 cancel_requested；请求中不可中断 → 阶段边界处理（同本地语义）。
    - rtf / peak_memory_gb 记 null（非本机推理）。
    - 失败 error 含 HTTP 状态与服务商消息，已脱敏（不含完整 key）。
    """
    jid = job["id"]
    jlog, fh, stage, cancelled = _job_context(jid)
    t_start = time.time()
    api_key = ""
    try:
        stage("preparing", "校验在线 provider")
        p = providers.get_raw(job.get("provider_id") or "")
        if not p:
            raise ValueError(f"Provider 不存在: {job.get('provider_id')}（可能已被删除）")
        if not p["enabled"]:
            raise ValueError(f"Provider「{p['name']}」已停用")
        api_key = p.get("api_key") or ""
        text = (job.get("target_text") or "").strip()
        if not text:
            raise ValueError("在线 TTS 需要 target_text")
        base_url = providers.validate_base_url(p["base_url"])  # 运行时再校验（纵深防御）
        host = urlparse(base_url).hostname or ""
        if cancelled():
            stage("cancelled", "用户在请求前取消")
            return

        stage("processing", f"在线 TTS 请求中（{p['name']} / {host}）")
        # 隐私：日志只记 provider/model/voice 与文本长度，不记 api_key
        jlog.info("在线 TTS: provider=%s model=%s voice=%s text_len=%d host=%s",
                  p["name"], p["model"], p["voice"], len(text), host)
        t_req = time.time()
        body, ctype, _status = providers.speech_request(
            base_url, api_key, p["model"], p["voice"], text, timeout=providers.JOB_TIMEOUT_S)
        req_wall = time.time() - t_req
        if not body:
            raise providers.ProviderError("服务端返回空响应")
        if cancelled():
            stage("cancelled", "请求已完成，但用户请求了取消；候选仍保留")

        stage("postprocessing", "保存候选音频")
        ext = _candidate_ext(body, ctype)
        out_path = config.OUTPUT_DIR / f"{jid}_candidate{ext}"
        out_path.write_bytes(body)
        meta = audio.probe(out_path)
        dur = meta["duration"]
        # 在线 TTS 无输入音频：注册音频记录（同 instruct_tts），使候选可存音色库 / 用作参考
        aid = db.new_id("aud")
        db.insert_audio({
            "id": aid, "original_name": f"在线TTS候选-{jid[-6:]}{ext}",
            "stored_path": str(out_path), "normalized_path": str(out_path),
            "format": meta["format"], "sample_rate": meta["sample_rate"],
            "channels": meta["channels"], "bit_depth": meta["bit_depth"],
            "duration": dur, "size_bytes": out_path.stat().st_size,
            "sha256": hashlib.sha256(body).hexdigest(),
        })
        fid = db.register_file(out_path, "candidate", job_id=jid, audio_id=aid, label="在线 TTS 候选（整段）")
        db.update_job(
            jid,
            status="cancelled" if cancelled() else "completed",
            stage_detail="完成",
            output_path=str(out_path),
            output_duration=dur,
            elapsed_s=time.time() - t_start,
            peak_memory_gb=None,  # 非本机推理
            rtf=None,
            finished_at=time.time(),
        )
        jlog.info("输出 %s (%.2fs @ %dHz, %s) 请求耗时 %.1fs", out_path, dur, meta["sample_rate"], ext, req_wall)
        jlog.info("结果文件ID: %s", fid)
    except Exception as e:  # noqa: BLE001
        err = providers.redact(f"{type(e).__name__}: {e}", api_key)
        jlog.error("任务失败: %s\n%s", err, traceback.format_exc())
        db.update_job(jid, status="failed", error=err[:2000], finished_at=time.time(),
                      elapsed_s=time.time() - t_start, stage_detail="失败")
    finally:
        jlog.removeHandler(fh)
        fh.close()
        db.worker_heartbeat(os.getpid(), current_job_id=None)


def run_job(job: dict, holder: EngineHolder) -> None:
    kind = job.get("kind") or "infer"
    if kind == "install":
        _run_model_job(job, model_manager.run_install)
        return
    if kind == "verify":
        _run_model_job(job, model_manager.run_verify)
        return
    provider_id = job.get("provider_id")
    if provider_id and provider_id != "local":
        run_online_tts(job)
        return

    jid = job["id"]
    jlog, fh, stage, cancelled = _job_context(jid)
    t_start = time.time()
    try:
        stage("preparing", "校验输入与构造指令")
        mode = job.get("mode") or "replace"
        aud = None
        src = None
        if mode != "instruct_tts":
            audio_id = job.get("audio_id")
            if not audio_id and job.get("voice_id"):
                ref = voices.resolve_audio(job["voice_id"])
                audio_id = ref["id"] if ref else None
            aud = db.get_audio(audio_id) if audio_id else None
            if not aud:
                raise ValueError("原始音频不存在")
            src = aud["normalized_path"] or aud["stored_path"]
            if not Path(src).exists():
                raise FileNotFoundError(f"音频文件缺失: {src}")
        instruction = build_instruction(job)
        db.update_job(jid, final_instruction=instruction)
        jlog.info("指令: %s", instruction)

        gen_seconds = job.get("gen_seconds")
        if gen_seconds is None:
            src_dur = (aud.get("duration") if aud else 0) or 0
            tgt = (job.get("target_text") or "").strip()
            if mode in ("full", "tts") and tgt:
                # 全文替换/零样本 TTS：按目标文本长度估算时长（中文约 4 字/秒 + 0.5s 余量），
                # 不短于源音频，避免新台词更长时被截断。用户显式指定时优先。
                gen_seconds = max(src_dur, len(tgt) / 4.0 + 0.5)
            elif mode == "instruct_tts" and tgt:
                # 指令 TTS 无参考音频：仅按文本长度估算
                gen_seconds = len(tgt) / 4.0 + 0.5
            else:
                gen_seconds = src_dur or None
        if cancelled():
            stage("cancelled", "用户在准备阶段取消")
            return

        # 内存压力护栏
        level = audio.memory_pressure_level()
        if level >= 4:
            raise RuntimeError("系统内存压力处于 critical，已暂停推理以保护系统；请关闭其他大内存应用后重试")

        stage("loading_model", "加载/复用模型")
        bits = job.get("bits")
        sequential = bool(job.get("sequential"))
        variant = job.get("model_variant") or "flash"
        t_load = time.time()
        engine = holder.ensure(variant, bits, sequential)
        db.worker_heartbeat(os.getpid(), model_loaded=1, model_variant=variant,
                            bits=bits, sequential=int(sequential), current_job_id=jid,
                            load_seconds=holder.load_seconds)
        jlog.info("模型就绪（加载耗时 %.1fs，复用=%s）", time.time() - t_load, holder.load_seconds is not None)
        if cancelled():
            stage("cancelled", "用户在加载阶段取消")
            return

        nfe = job.get("nfe") or 32
        steps_desc = "4 步固定" if variant == "flash" else f"{nfe} 步"
        stage("processing", f"推理中（AuK-{variant} {steps_desc}，目标时长 {gen_seconds or '同源音频'}s）")
        from auk_mlx.infer import GenerateOptions

        t_gen = time.time()
        wav, sr = engine.generate(
            instruction,
            audio_path=src,  # instruct_tts 无参考音频 → None（引擎走 text-only 路径）
            opts=GenerateOptions(gen_seconds=gen_seconds, nfe=nfe, seed=job.get("seed")),
        )
        gen_wall = time.time() - t_gen
        if cancelled():
            stage("cancelled", "推理已完成，但用户请求了取消；候选仍保留")
            # 仍保存候选供检查
        import numpy as np
        import soundfile as sf

        stage("postprocessing", "保存候选音频")
        out_path = config.OUTPUT_DIR / f"{jid}_candidate.wav"
        sf.write(str(out_path), wav, sr, subtype="PCM_16")
        dur = len(wav) / sr
        peak = _peak_rss_gb()
        # instruct_tts 无输入音频：把候选注册为音频记录，使其可保存到音色库 / 用作参考音色
        cand_audio_id = job["audio_id"]
        if not cand_audio_id:
            aid = db.new_id("aud")
            db.insert_audio({
                "id": aid, "original_name": f"音色设计候选-{jid[-6:]}.wav",
                "stored_path": str(out_path), "normalized_path": str(out_path),
                "format": "wav", "sample_rate": sr, "channels": 1, "bit_depth": 16,
                "duration": dur, "size_bytes": out_path.stat().st_size, "sha256": "",
            })
            cand_audio_id = aid
        fid = db.register_file(out_path, "candidate", job_id=jid, audio_id=cand_audio_id, label="生成候选（整段）")
        db.update_job(
            jid,
            status="cancelled" if cancelled() else "completed",
            stage_detail="完成",
            output_path=str(out_path),
            output_duration=dur,
            elapsed_s=time.time() - t_start,
            peak_memory_gb=round(peak, 2),
            rtf=round(gen_wall / dur, 3) if dur else None,
            finished_at=time.time(),
        )
        jlog.info("输出 %s (%.2fs @ %dHz) 推理耗时 %.1fs RTF=%.2f 峰值RSS %.2fGB",
                  out_path, dur, sr, gen_wall, gen_wall / dur if dur else 0, peak)
        jlog.info("结果文件ID: %s", fid)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        jlog.error("任务失败: %s\n%s", err, traceback.format_exc())
        db.update_job(jid, status="failed", error=err[:2000], finished_at=time.time(),
                      elapsed_s=time.time() - t_start, stage_detail="失败")
    finally:
        jlog.removeHandler(fh)
        fh.close()
        db.worker_heartbeat(os.getpid(), current_job_id=None)


def main() -> None:
    _setup_logging()
    db.init_db()
    pid = os.getpid()
    log.info("worker 启动 pid=%s", pid)
    try:
        import mlx.core as mx

        log.info("MLX %s | device=%s | metal=%s", mx.__version__, mx.default_device(), mx.metal.is_available())
        db.worker_heartbeat(pid, mlx_version=mx.__version__, metal_available=int(mx.metal.is_available()),
                            device=str(mx.default_device()))
        if not mx.metal.is_available():
            log.error("Metal 不可用！推理将不可接受地慢或失败。请运行 doctor.sh 诊断。")
    except Exception as e:  # noqa: BLE001
        log.error("MLX 导入失败: %s", e)
        db.worker_heartbeat(pid, last_error=f"MLX 导入失败: {e}")
        sys.exit(1)

    interrupted = db.mark_interrupted_jobs()
    if interrupted:
        log.info("已将 %d 个遗留运行中任务标记为 failed（可重试）", interrupted)

    holder = EngineHolder()
    last_job_finish = time.time()
    db.worker_heartbeat(pid, model_loaded=0, started_at=time.time(), current_job_id=None, last_error="")

    while True:
        try:
            db.worker_heartbeat(pid, model_loaded=int(holder.loaded))
            settings = db.get_settings()
            idle_unload = int(settings.get("idle_unload_s", config.MODEL_IDLE_UNLOAD_S))

            if db.consume_unload_request():
                holder.unload()
                db.worker_heartbeat(pid, model_loaded=0)
            elif holder.loaded and idle_unload > 0 and time.time() - last_job_finish > idle_unload:
                log.info("空闲超过 %ss，自动卸载模型", idle_unload)
                holder.unload()
                db.worker_heartbeat(pid, model_loaded=0)

            # 激活请求：仅在任务间隙消费；与当前 key 不同则 unload + ensure，
            # 不强制卸载运行中模型（运行中不会进入此分支）。
            activate = db.consume_activate_request()
            if activate:
                try:
                    if holder.loaded and holder.key and holder.key[0] != activate:
                        holder.unload()
                        db.worker_heartbeat(pid, model_loaded=0)
                    if not holder.loaded:
                        bits_s = str(settings.get("default_bits", config.DEFAULT_BITS))
                        bits = int(bits_s) if bits_s.isdigit() else None
                        seq = settings.get("default_sequential", "0") == "1"
                        holder.ensure(activate, bits, seq)
                        db.worker_heartbeat(pid, model_loaded=1, model_variant=activate,
                                            bits=bits, sequential=int(seq),
                                            load_seconds=holder.load_seconds)
                        log.info("已按请求激活 variant=%s（加载 %.1fs）", activate, holder.load_seconds or 0)
                    last_job_finish = time.time()  # 重置空闲计时，避免刚激活即被空闲卸载
                except Exception as e:  # noqa: BLE001
                    log.error("激活 %s 失败: %s", activate, e)
                    db.worker_heartbeat(pid, last_error=f"激活 {activate} 失败: {e}")

            job = db.claim_next_job(pid)
            if job:
                # 排队期间被取消的任务
                if job.get("cancel_requested"):
                    db.update_job(job["id"], status="cancelled", finished_at=time.time(), stage_detail="排队时取消")
                else:
                    run_job(job, holder)
                last_job_finish = time.time()
            else:
                time.sleep(config.WORKER_POLL_S)
        except KeyboardInterrupt:
            log.info("worker 收到中断，退出")
            break
        except Exception as e:  # noqa: BLE001
            log.error("worker 循环异常: %s\n%s", e, traceback.format_exc())
            db.worker_heartbeat(pid, last_error=str(e)[:500])
            time.sleep(2)

    holder.unload()
    db.worker_heartbeat(pid, model_loaded=0, current_job_id=None)


if __name__ == "__main__":
    main()