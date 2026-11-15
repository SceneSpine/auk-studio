"""模型安装管理器（manifest 驱动，docs/API_CONTRACT.md §models）。

原则：
- 先探测已存在文件，**绝不重复下载/转换**（BASELINE §5）。
- 下载只允许 allowlist 源：ModelScope Tencent-Hunyuan/AuK-Flash、Tencent-Hunyuan/AuK、
  Qwen/Qwen2.5-Omni-3B 及 HF 同名仓库；渠道逻辑复用 scripts/download_models.py。
- 断点续传：.part + .progress（与既有下载脚本同格式，可互相续传）。
- convert/quantize 用参数化 subprocess（[venv_python, -m, auk_mlx.convert, ...]，
  cwd=AuK，PYTHONPATH=AuK/src），不拼 shell。
- 原始权重只读保护：不覆盖/不删除已存在的原始文件；哈希不一致只报告 broken。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from . import config, db

ALLOWED_HOSTS = {"modelscope.cn", "huggingface.co"}
TEMP_MARGIN_GB = 2.0  # 转换临时空间余量


class Cancelled(Exception):
    """安装/校验任务被用户取消（阶段边界）。"""


# ---------------- registry / manifest ----------------

def registry_path() -> Path:
    env = os.environ.get("AUK_MODELS_REGISTRY")
    return Path(env).expanduser() if env else config.ROOT / "config" / "models_registry.json"


def manifest_path() -> Path:
    env = os.environ.get("AUK_MODEL_MANIFEST")
    return Path(env).expanduser() if env else config.ROOT / "config" / "model_manifest.json"


def load_registry() -> dict:
    data = json.loads(registry_path().read_text(encoding="utf-8"))
    return data


def load_manifest() -> dict:
    try:
        return json.loads(manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_entry(model_id: str) -> dict | None:
    for m in load_registry()["models"]:
        if m["id"] == model_id:
            return m
    return None


def raw_path(entry: dict, rel: str) -> Path:
    return config.MODELS_DIR / entry["raw_dir"] / rel


def mlx_path(rel: str) -> Path:
    return config.MLX_DIR / rel


def all_files(entry: dict) -> list[str]:
    return list(entry.get("required_files", [])) + list(entry.get("optional_files", []))


# ---------------- state detection ----------------

def _size_gb(p: Path) -> float:
    try:
        return p.stat().st_size / 1e9
    except OSError:
        return 0.0


def _du_gb(path: Path) -> float | None:
    try:
        out = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True, timeout=20)
        if out.returncode == 0:
            return round(int(out.stdout.split()[0]) * 1024 / 1e9, 2)
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    return None


def _total_memory_gb() -> float:
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip()) / 1e9
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def memory_fit() -> str:
    import platform
    # 内存适配评估仅针对本地推理（Apple Silicon + macOS 统一内存）；其余平台无意义
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return "unknown"
    total = _total_memory_gb()
    if total >= 32:
        return "comfortable"
    if total >= 16:
        return "tight"
    return "insufficient"


def model_state(entry: dict) -> dict:
    """探测文件齐全度（无副作用）。state: ready/not_installed/downloading/verifying/converting/broken。"""
    manifest = load_manifest().get(entry["manifest_key"], {})
    missing_required = [r for r in entry.get("required_files", []) if not raw_path(entry, r).exists()]
    missing_optional = [r for r in entry.get("optional_files", []) if not raw_path(entry, r).exists()]
    missing_converted = [r for r in entry.get("converted_files", []) if not mlx_path(r).exists()]
    missing_quantized = [r for r in entry.get("quantized_files", []) if not mlx_path(r).exists()]

    downloaded = not missing_required
    converted = not missing_converted
    quantized = bool(entry.get("quantized_files")) and not missing_quantized

    # 原始文件大小与 manifest 不一致 → broken（不触碰文件，只报告）
    size_bad = []
    for rel in entry.get("required_files", []):
        p = raw_path(entry, rel)
        meta = manifest.get(rel) or {}
        if p.exists() and meta.get("size") and p.stat().st_size != meta["size"]:
            size_bad.append(rel)

    state, detail = "ready", ""
    if size_bad:
        state = "broken"
        detail = "原始文件大小与 manifest 不一致（可能损坏）：" + ", ".join(size_bad) + "。请运行校验或重新安装。"
    elif missing_required:
        state = "not_installed"
        detail = "缺失原始权重：" + ", ".join(missing_required[:6]) + ("…" if len(missing_required) > 6 else "")
    elif missing_converted:
        state = "not_installed"
        detail = ("原始权重已存在（将复用，不重新下载），缺少 MLX 转换产物："
                  + ", ".join(missing_converted) + "。安装时将执行转换。")
    else:
        # 最近一次校验失败 → broken
        last_verify = db.last_model_job(entry["id"], "verify")
        if last_verify and last_verify["status"] == "failed":
            state = "broken"
            detail = "最近一次 sha256 校验失败：" + (last_verify.get("error") or "")[:300]

    # 安装任务进行中 → 覆盖为过程态
    active = db.active_model_job(entry["id"])
    if active and active["status"] in ("queued", "preparing", "loading_model", "processing", "postprocessing"):
        phase = ""
        try:
            phase = (json.loads(active.get("install_json") or "{}") or {}).get("phase", "")
        except ValueError:
            pass
        if active["kind"] == "verify":
            state = "verifying"
        elif phase in ("download", "prepare"):
            state = "downloading"
        elif phase == "verify":
            state = "verifying"
        elif phase in ("convert", "quantize"):
            state = "converting"
        else:
            state = "downloading" if active["kind"] == "install" else "verifying"
        detail = f"任务 {active['id']} 进行中（{active['status']}）。"

    # sizes
    download_gb = round(sum((manifest.get(r) or {}).get("size", 0) for r in all_files(entry)) / 1e9, 2)
    converted_gb = round(sum(_size_gb(mlx_path(r)) for r in
                             entry.get("converted_files", []) + entry.get("quantized_files", [])
                             if mlx_path(r).exists()), 2)
    if entry["id"] == "vae":
        disk_gb = round(sum(_size_gb(raw_path(entry, r)) for r in all_files(entry) if raw_path(entry, r).exists())
                        + converted_gb, 2)
    else:
        raw_du = _du_gb(config.MODELS_DIR / entry["raw_dir"])
        if raw_du is None:
            raw_du = round(sum(_size_gb(raw_path(entry, r)) for r in all_files(entry)
                               if raw_path(entry, r).exists()), 2)
        disk_gb = round(raw_du + converted_gb, 2)

    return {
        "state": state, "state_detail": detail or None,
        "downloaded": downloaded, "converted": converted, "quantized": quantized,
        "missing_required": missing_required, "missing_optional": missing_optional,
        "missing_converted": missing_converted, "missing_quantized": missing_quantized,
        "size": {"download_gb": download_gb, "converted_gb": converted_gb, "disk_gb": disk_gb},
    }


def model_info(entry: dict, ws: dict | None = None) -> dict:
    registry = load_registry()
    st = model_state(entry)
    lic = registry["licenses"][entry["license_id"]]
    ws = ws if ws is not None else (db.get_worker_state() or {})
    variant = entry.get("variant")
    active = bool(variant and ws.get("model_loaded") and ws.get("model_variant") == variant)
    return {
        "id": entry["id"],
        "display_name": entry["display_name"],
        "family": entry.get("family", ""),
        "role": entry.get("role", "main"),
        "description": entry.get("description", ""),
        "source": entry["source"],
        "license": lic,
        "state": st["state"],
        "state_detail": st["state_detail"],
        "downloaded": st["downloaded"],
        "converted": st["converted"],
        "quantized": st["quantized"],
        "size": st["size"],
        "memory_fit": memory_fit(),
        "depends_on": entry.get("depends_on", []),
        "active": active,
    }


# ---------------- install plan ----------------

def involved_licenses(entry: dict) -> list[dict]:
    registry = load_registry()
    ids = [entry["license_id"]]
    for dep in entry.get("depends_on", []):
        dep_entry = get_entry(dep)
        if dep_entry and dep_entry["license_id"] not in ids:
            ids.append(dep_entry["license_id"])
    return [registry["licenses"][i] for i in ids]


def build_install_plan(model_id: str) -> dict:
    entry = get_entry(model_id)
    if entry is None:
        raise KeyError(model_id)
    st = model_state(entry)
    manifest = load_manifest().get(entry["manifest_key"], {})
    usage = __import__("shutil").disk_usage(config.MODELS_DIR if config.MODELS_DIR.exists() else config.ROOT)
    free_gb = round(usage.free / 1e9, 1)
    licenses = involved_licenses(entry)
    warnings: list[str] = []
    if any(not lic["commercial"] for lic in licenses):
        warnings.append("涉及 Qwen Research License：仅限非商业研究/评估，商用需另行授权（docs/MODEL_LICENSES.md）。")

    if st["state"] == "ready":
        steps = [
            {"kind": "reuse", "label": "复用原始权重", "detail": f"{entry['raw_dir']}/ 文件齐全，不重新下载。",
             "size_gb": st["size"]["download_gb"]},
            {"kind": "reuse", "label": "复用 MLX 转换产物", "detail": "mlx-converted/ 产物齐全，不重新转换。",
             "size_gb": st["size"]["converted_gb"]},
        ]
        if entry.get("quantized_files"):
            steps.append({"kind": "reuse", "label": "复用 8-bit 量化副本", "detail": "q8 副本已存在。"})
        return {
            "model_id": model_id, "steps": steps, "total_download_gb": 0.0, "extra_disk_gb": 0.0,
            "disk_free_gb": free_gb, "disk_ok": True, "licenses": licenses,
            "requires_consent": False, "already_ready": True, "warnings": warnings,
        }

    steps = []
    missing_download = [r for r in all_files(entry) if not raw_path(entry, r).exists()]
    total_download = sum((manifest.get(r) or {}).get("size", 0) for r in missing_download)
    if missing_download:
        steps.append({
            "kind": "download", "label": "下载原始权重",
            "detail": f"{len(missing_download)} 个文件：" + ", ".join(missing_download[:8])
                      + ("…" if len(missing_download) > 8 else "")
                      + "。主渠道 ModelScope（直连），备渠道 HuggingFace（走代理）；断点续传。",
            "size_gb": round(total_download / 1e9, 2),
            "source": entry["source"]["repo"],
        })
    else:
        steps.append({"kind": "reuse", "label": "复用原始权重",
                      "detail": "原始权重已存在，跳过下载。", "size_gb": st["size"]["download_gb"]})

    steps.append({"kind": "verify", "label": "sha256 校验",
                  "detail": "逐文件对照 config/model_manifest.json（HF 官方 sha256）。"})

    extra_convert = 0.0
    for cs in entry.get("convert_steps", []):
        if any(not mlx_path(o).exists() for o in cs["outputs"]):
            src = config.MODELS_DIR / cs["src"][0] / cs["src"][1] if cs["src"][1] else config.MODELS_DIR / cs["src"][0]
            steps.append({
                "kind": "convert", "label": f"转换 {cs['kind']}",
                "detail": f"auk_mlx.convert {cs['kind']} {src} → mlx-converted/{cs['dst']}（参数化 subprocess）。",
                "size_gb": cs.get("output_gb"),
            })
            extra_convert += cs.get("output_gb", 0.0)
    q = entry.get("quantize")
    if q and any(not mlx_path(o).exists() for o in q["outputs"]):
        steps.append({"kind": "quantize", "label": "8-bit 量化副本",
                      "detail": f"auk_mlx.convert quantize --bits 8 --variant {q['variant']}（官方推荐精度）。",
                      "size_gb": q.get("output_gb")})
        extra_convert += q.get("output_gb", 0.0)
    steps.append({"kind": "smoke", "label": "烟测（可选）",
                  "detail": "安装完成后在工作台提交一个短音频任务验证推理链路。"})

    extra_disk = round(total_download / 1e9 + extra_convert + TEMP_MARGIN_GB, 2)
    disk_ok = free_gb >= extra_disk
    if not disk_ok:
        warnings.append(f"磁盘余量 {free_gb}GB 小于预计需求 {extra_disk}GB（含转换临时空间）。")
    if st["state"] == "broken":
        warnings.append("当前状态 broken：" + (st["state_detail"] or ""))

    return {
        "model_id": model_id, "steps": steps,
        "total_download_gb": round(total_download / 1e9, 2),
        "extra_disk_gb": extra_disk, "disk_free_gb": free_gb, "disk_ok": disk_ok,
        "licenses": licenses, "requires_consent": True, "already_ready": False,
        "warnings": warnings,
    }


# ---------------- execution (worker side) ----------------

_dl_script = None


def _download_script():
    """复用 scripts/download_models.py 的渠道逻辑（urls_for / fetch_range / sha256_file / CHUNK）。"""
    global _dl_script
    if _dl_script is None:
        path = config.ROOT / "scripts" / "download_models.py"
        spec = importlib.util.spec_from_file_location("auk_studio_download_models", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _dl_script = mod
    return _dl_script


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _check_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise RuntimeError(f"下载源不在 allowlist：{host}（仅允许 modelscope.cn / huggingface.co）")


def download_file(entry: dict, rel: str, meta: dict, ctx) -> str:
    """单文件下载（断点续传，串行分块）。返回 'reused' | 'downloaded'。"""
    dst = raw_path(entry, rel)
    if dst.exists():
        ctx.log(f"↷ 复用已存在文件：{rel}（不重复下载）")
        return "reused"
    size = int(meta["size"])
    expect = meta.get("sha256")
    dst.parent.mkdir(parents=True, exist_ok=True)
    script = _download_script()
    chunk = script.CHUNK
    part = Path(str(dst) + ".part")
    prog = Path(str(dst) + ".progress")
    n_chunks = max(1, math.ceil(size / chunk))
    done: set[int] = set()
    if part.exists() and part.stat().st_size == size and prog.exists():
        try:
            done = set(json.loads(prog.read_text()))
            ctx.log(f"↻ 续传 {rel}：{len(done)}/{n_chunks} 块已完成")
        except ValueError:
            done = set()
    if not done:
        with open(part, "wb") as f:
            f.truncate(size)
    repo = {"ms": entry["source"]["repo"], "hf": entry["source"]["hf_repo"]}
    urls = script.urls_for(repo, rel)
    for u in urls.values():
        _check_url(u)

    for i in range(n_chunks):
        if i in done:
            continue
        if ctx.cancelled():
            raise Cancelled(f"下载 {rel} 时取消（已下载块已保存，可续传）")
        start = i * chunk
        end = min(size - 1, start + chunk - 1)
        data = None
        last_err = None
        for attempt in range(6):
            source = "ms" if attempt < 4 else "hf"
            try:
                data = script.fetch_range(urls[source], start, end, source)
                if len(data) != end - start + 1:
                    raise IOError(f"short read {len(data)} != {end - start + 1}")
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                data = None
                if ctx.cancelled():
                    raise Cancelled(f"下载 {rel} 时取消（可续传）")
                time.sleep(min(2 ** attempt, 15))
        if data is None:
            raise RuntimeError(f"{rel} 块 {i} 下载失败（已重试）：{last_err}")
        with open(part, "r+b") as f:
            f.seek(start)
            f.write(data)
        done.add(i)
        prog.write_text(json.dumps(sorted(done)))
        ctx.progress("download", min(size, len(done) * chunk), size, None, None,
                     f"{rel}: {len(done)}/{n_chunks} 块")
    if expect:
        ctx.log(f"校验 sha256：{rel} …")
        actual = sha256_file(part)
        if actual != expect:
            part.unlink(missing_ok=True)
            prog.unlink(missing_ok=True)
            raise RuntimeError(f"sha256 不一致：{rel}（{actual} != {expect}）")
    os.replace(part, dst)
    prog.unlink(missing_ok=True)
    ctx.log(f"✓ 下载完成：{rel}（{size / 1e9:.2f} GB）")
    return "downloaded"


def verify_raw(entry: dict, ctx) -> tuple[bool, list[dict]]:
    """对原始权重逐文件 sha256/大小对照 manifest。"""
    manifest = load_manifest().get(entry["manifest_key"], {})
    results = []
    ok = True
    files = all_files(entry)
    for idx, rel in enumerate(files):
        if ctx.cancelled():
            raise Cancelled("校验时取消")
        p = raw_path(entry, rel)
        meta = manifest.get(rel) or {}
        required = rel in entry.get("required_files", [])
        if not p.exists():
            results.append({"file": rel, "status": "missing", "required": required})
            if required:
                ok = False
            ctx.log(f"✗ 缺失：{rel}" + ("" if required else "（可选）"))
            continue
        expect = meta.get("sha256")
        if expect:
            actual = sha256_file(p)
            status = "ok" if actual == expect else "mismatch"
            results.append({"file": rel, "status": status, "expected": expect, "actual": actual})
            if status != "ok":
                ok = False
                ctx.log(f"✗ sha256 不一致：{rel}\n  期望 {expect}\n  实际 {actual}")
            else:
                ctx.log(f"✓ sha256 通过：{rel}")
        elif meta.get("size"):
            actual_size = p.stat().st_size
            status = "ok" if actual_size == meta["size"] else "size_mismatch"
            results.append({"file": rel, "status": status, "expected_size": meta["size"], "actual_size": actual_size})
            if status != "ok":
                ok = False
                ctx.log(f"✗ 大小不一致：{rel}（{actual_size} != {meta['size']}）")
            else:
                ctx.log(f"✓ 大小通过：{rel}")
        else:
            results.append({"file": rel, "status": "ok", "note": "manifest 无校验信息，仅检查存在性"})
        ctx.progress("verify", None, None, idx + 1, len(files), f"校验 {rel}")
    return ok, results


def _run_convert(args: list[str], ctx, need_gb: float) -> None:
    free = __import__("shutil").disk_usage(config.MODELS_DIR).free / 1e9
    if free < need_gb:
        raise RuntimeError(f"磁盘不足：转换需要约 {need_gb:.1f}GB，剩余 {free:.1f}GB")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(config.AUK_REPO / "src")
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    cmd = [str(config.VENV_PYTHON), "-m", "auk_mlx.convert", *args]
    ctx.log("执行（参数化，无 shell）：" + " ".join(cmd))
    proc = subprocess.Popen(
        cmd, cwd=str(config.AUK_REPO), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        for line in proc.stdout:
            ctx.log(line.rstrip())
            if ctx.cancelled():
                proc.terminate()
                raise Cancelled("转换阶段取消（产物可重新转换）")
        rc = proc.wait()
    finally:
        if proc.poll() is None:
            proc.terminate()
    if rc != 0:
        raise RuntimeError(f"auk_mlx.convert 失败（exit={rc}），详见任务日志")


def run_install(job: dict, ctx) -> None:
    """kind=install 任务：download → verify → convert → quantize（串行，可取消/续传）。"""
    entry = get_entry(job["model_id"])
    if entry is None:
        raise RuntimeError(f"未知模型 {job['model_id']}")
    manifest = load_manifest().get(entry["manifest_key"], {})
    ctx.stage("preparing", "准备安装：探测已存在文件")
    ctx.progress("prepare", 0, 0, 0, 0, "探测复用")

    missing_download = [r for r in all_files(entry) if not raw_path(entry, r).exists()]
    need_convert = [cs for cs in entry.get("convert_steps", [])
                    if any(not mlx_path(o).exists() for o in cs["outputs"])]
    q = entry.get("quantize")
    need_quantize = bool(q and any(not mlx_path(o).exists() for o in q["outputs"]))
    download_bytes = sum(int((manifest.get(r) or {}).get("size", 0)) for r in missing_download)
    convert_gb = sum(cs.get("output_gb", 0) for cs in need_convert) + (q.get("output_gb", 0) if need_quantize else 0)
    free = __import__("shutil").disk_usage(config.MODELS_DIR).free / 1e9
    need_gb = download_bytes / 1e9 + convert_gb + TEMP_MARGIN_GB
    if free < need_gb:
        raise RuntimeError(f"磁盘不足：安装需要约 {need_gb:.1f}GB（含转换临时空间），剩余 {free:.1f}GB。请清理磁盘后重试。")
    ctx.log(f"磁盘检查通过：需 {need_gb:.1f}GB，余 {free:.1f}GB；缺失下载 {len(missing_download)} 文件，"
            f"待转换 {len(need_convert)} 步，量化={'是' if need_quantize else '否'}")
    reused_count = len(all_files(entry)) - len(missing_download)
    if reused_count:
        ctx.log(f"↷ 复用已存在文件 {reused_count} 个（不重复下载）")

    # ---- download ----
    ctx.stage("processing", "下载原始权重（ModelScope 主渠道 / HF 备渠道，断点续传）")
    total_bytes = sum(int((manifest.get(r) or {}).get("size", 0)) for r in all_files(entry))
    files_total = len(all_files(entry))
    files_done = files_total - len(missing_download)
    reused_bytes = total_bytes - download_bytes
    ctx.progress("download", reused_bytes, total_bytes, files_done, files_total, "开始下载")
    for rel in sorted(missing_download, key=lambda r: (manifest.get(r) or {}).get("size", 0)):
        if ctx.cancelled():
            raise Cancelled("下载阶段取消（可续传）")
        meta = manifest.get(rel)
        if not meta:
            ctx.log(f"⚠ manifest 未收录 {rel}，跳过（非必需）")
            files_done += 1
            continue
        base = reused_bytes

        def _progress(phase, dl, tot, fd, ft, detail):
            ctx.progress(phase, base + (dl or 0), total_bytes, files_done, files_total, detail)

        class _Sub:
            log = staticmethod(ctx.log)
            cancelled = staticmethod(ctx.cancelled)
            progress = staticmethod(_progress)

        download_file(entry, rel, meta, _Sub())
        files_done += 1
        reused_bytes += int(meta["size"])
        ctx.progress("download", reused_bytes, total_bytes, files_done, files_total, f"完成 {rel}")

    # ---- verify ----
    if ctx.cancelled():
        raise Cancelled("校验前取消")
    ctx.stage("processing", "sha256 校验原始权重")
    ok, results = verify_raw(entry, ctx)
    bad = [r["file"] for r in results if r["status"] in ("mismatch", "size_mismatch", "missing") and r.get("required", True)]
    if not ok:
        raise RuntimeError("校验失败：" + ", ".join(bad) + "。原始权重可能损坏；为保护数据未自动删除，请人工确认后重新安装。")

    # ---- convert ----
    for cs in need_convert:
        if ctx.cancelled():
            raise Cancelled("转换前取消")
        src = config.MODELS_DIR / cs["src"][0] / cs["src"][1] if cs["src"][1] else config.MODELS_DIR / cs["src"][0]
        if not src.exists():
            raise RuntimeError(f"转换源缺失：{src}（依赖组件未安装？）")
        ctx.stage("processing", f"转换 {cs['kind']} → mlx-converted/{cs['dst']}")
        ctx.progress("convert", None, None, None, None, f"auk_mlx.convert {cs['kind']}")
        _run_convert([cs["kind"], str(src), str(mlx_path(cs["dst"]))], ctx, cs.get("output_gb", 0) + TEMP_MARGIN_GB)

    # ---- quantize ----
    if need_quantize:
        if ctx.cancelled():
            raise Cancelled("量化前取消")
        ctx.stage("processing", f"写 8-bit 量化副本（variant={q['variant']}）")
        ctx.progress("quantize", None, None, None, None, "auk_mlx.convert quantize --bits 8")
        _run_convert(["quantize", str(config.MLX_DIR), "--bits", "8", "--variant", q["variant"]],
                     ctx, q.get("output_gb", 0) + TEMP_MARGIN_GB)

    ctx.progress("done", total_bytes, total_bytes, files_total, files_total, "安装完成")
    ctx.log("✓ 安装完成：download → verify → convert → quantize 全部通过")


def run_verify(job: dict, ctx) -> None:
    """kind=verify 任务：原始权重 sha256 对照 manifest。"""
    entry = get_entry(job["model_id"])
    if entry is None:
        raise RuntimeError(f"未知模型 {job['model_id']}")
    ctx.stage("processing", "sha256 校验原始权重")
    ok, results = verify_raw(entry, ctx)
    summary = "; ".join(f"{r['file']}: {r['status']}" for r in results)
    ctx.progress("done" if ok else "verify", None, None, len(results), len(results), summary[:1500])
    if not ok:
        bad = [r["file"] for r in results if r["status"] != "ok"]
        raise RuntimeError("以下文件校验未通过：" + ", ".join(bad))
    ctx.log("✓ 全部文件校验通过")