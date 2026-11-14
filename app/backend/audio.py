"""音频处理：探测、标准化、波形峰值、拼接导出。

原则（方案 §8）：
- 原始上传文件永远只读保留。
- 模型输入标准化为 24kHz mono WAV（工作副本），保留映射信息。
- 模型输出是整段重生成候选；拼回完整音频时未修改区域使用原始 PCM。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

MODEL_SR = 24000


def probe(path: str | Path) -> dict:
    """ffprobe 获取容器/流信息。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise ValueError(f"无法解析音频文件: {out.stderr.strip()[:300]}")
    data = json.loads(out.stdout)
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if stream is None:
        raise ValueError("文件中没有音频流")
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or stream.get("duration") or 0)
    bits = stream.get("bits_per_raw_sample") or stream.get("bits_per_sample")
    return {
        "format": (fmt.get("format_name") or "").split(",")[0],
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "bit_depth": int(bits) if bits and str(bits).isdigit() else None,
        "duration": duration,
        "size_bytes": int(fmt.get("size") or Path(path).stat().st_size),
    }


def _read_any(src: str | Path) -> tuple[np.ndarray, int]:
    """读取任意 ffmpeg 支持的音频。libsndfile 不支持的格式（m4a/aac 等）回退 ffmpeg。"""
    try:
        return sf.read(str(src), dtype="float32", always_2d=True)
    except Exception:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-acodec", "pcm_f32le", tmp_path],
                capture_output=True, text=True, timeout=300,
            )
            if r.returncode != 0:
                raise ValueError(f"ffmpeg 解码失败: {r.stderr.strip()[:200]}")
            return sf.read(tmp_path, dtype="float32", always_2d=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


def normalize(src: str | Path, dst: str | Path) -> dict:
    """标准化为模型输入：24kHz mono float32 WAV。返回元信息。"""
    wav, sr = _read_any(src)
    wav = wav.mean(axis=1)
    if sr != MODEL_SR:
        wav = soxr.resample(wav, sr, MODEL_SR, quality="VHQ")
    wav = np.ascontiguousarray(wav, dtype=np.float32)
    sf.write(str(dst), wav, MODEL_SR, subtype="FLOAT")
    return {"sample_rate": MODEL_SR, "channels": 1, "duration": len(wav) / MODEL_SR}


def waveform_peaks(path: str | Path, n_points: int = 2400) -> dict:
    """min/max 峰值包络，供前端波形渲染。"""
    wav, sr = sf.read(str(path), dtype="float32", always_2d=True)
    wav = wav.mean(axis=1)
    n = len(wav)
    if n == 0:
        return {"points": [], "duration": 0.0, "sample_rate": sr}
    step = max(1, n // n_points)
    trimmed = wav[: (n // step) * step].reshape(-1, step)
    mins = trimmed.min(axis=1)
    maxs = trimmed.max(axis=1)
    points = [[round(float(a), 4), round(float(b), 4)] for a, b in zip(mins, maxs)]
    return {"points": points, "duration": n / sr, "sample_rate": sr}


def _fade(n: int) -> np.ndarray:
    """raised-cosine 淡化曲线（0→1）。"""
    if n <= 0:
        return np.ones(0, dtype=np.float32)
    return (0.5 - 0.5 * np.cos(np.pi * np.arange(n, dtype=np.float32) / max(1, n - 1))).astype(np.float32)


def _join(a: np.ndarray, b: np.ndarray, xf: int) -> np.ndarray:
    """交叉淡化拼接两段（同采样率、同声道布局，shape [N, C]）。"""
    xf = min(xf, len(a), len(b))
    if xf <= 0:
        return np.concatenate([a, b], axis=0)
    fade = _fade(xf)[:, None]
    overlap = a[-xf:] * (1 - fade) + b[:xf] * fade
    return np.concatenate([a[:-xf], overlap, b[xf:]], axis=0)


def splice(
    original_path: str | Path,
    candidate_path: str | Path,
    out_path: str | Path,
    *,
    start_s: float,
    end_s: float,
    cand_start_s: float = 0.0,
    cand_end_s: float | None = None,
    crossfade_ms: int = 30,
) -> dict:
    """把候选片段拼回原始音频。

    - 原始音频按其原生采样率/声道读取，未修改区域保留原始 PCM。
    - 候选（24kHz mono）重采样到原始采样率；立体声原始则复制到两声道。
    - [start_s, end_s) 为原始时间轴上被替换的区间；
      [cand_start_s, cand_end_s) 为候选中用于插入的部分（默认整段候选）。
    """
    orig, osr = _read_any(original_path)
    cand, csr = _read_any(candidate_path)
    cand = cand.mean(axis=1, keepdims=True)
    if csr != osr:
        cand = soxr.resample(cand, csr, osr, quality="VHQ")
    if cand.shape[1] == 1 and orig.shape[1] > 1:
        cand = np.repeat(cand, orig.shape[1], axis=1)

    n = len(orig)
    s = int(np.clip(round(start_s * osr), 0, n))
    e = int(np.clip(round(end_s * osr), s, n))
    cs = int(np.clip(round(cand_start_s * osr), 0, len(cand)))
    ce = int(np.clip(round(cand_end_s * osr), cs, len(cand))) if cand_end_s is not None else len(cand)
    piece = cand[cs:ce]
    if len(piece) == 0:
        raise ValueError("候选片段为空")

    xf = max(0, int(crossfade_ms * osr / 1000))
    head, tail = orig[:s], orig[e:]
    result = _join(_join(head, piece, xf), tail, xf)
    sf.write(str(out_path), result, osr, subtype="PCM_16")
    return {
        "sample_rate": osr,
        "channels": int(orig.shape[1]),
        "duration": len(result) / osr,
        "replaced_region_s": [s / osr, e / osr],
        "inserted_s": len(piece) / osr,
        "crossfade_ms": crossfade_ms,
    }


def trim(src: str | Path, dst: str | Path, start_s: float, end_s: float) -> dict:
    wav, sr = sf.read(str(src), dtype="float32", always_2d=True)
    s = int(np.clip(round(start_s * sr), 0, len(wav)))
    e = int(np.clip(round(end_s * sr), s, len(wav)))
    sf.write(str(dst), wav[s:e], sr, subtype="PCM_16")
    return {"duration": (e - s) / sr, "sample_rate": sr}


def memory_pressure_level() -> int:
    """macOS 内存压力等级：1=normal, 2=warn, 4=critical。失败返回 0。"""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            capture_output=True, text=True, timeout=5,
        )
        return int(out.stdout.strip())
    except Exception:
        return 0