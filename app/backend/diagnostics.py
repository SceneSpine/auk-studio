"""系统资源探针与运行前评估（docs/API_CONTRACT.md §diagnostics/preflight）。

原则：
- 真实探针：sysctl / vm_stat / df / du / --version；观测值与估计值用 measured 区分。
- Apple 统一内存不能只看 free RAM：结合内存压力、swap、模型峰值经验。
- 不在 HTTP 请求里跑 GPU：MLX/Metal 状态取 worker 心跳（worker 启动时真实导入并运行）。
- 不伪造 GPU 占用百分比。
- 结果缓存 5s，避免重复 subprocess。
"""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
import time

from . import audio, capabilities, config, db

CACHE_TTL_S = 5.0
_cache: dict[tuple, tuple[float, dict]] = {}

PRESSURE_LABELS = {1: "正常", 2: "偏高", 4: "严重"}


def _run(cmd: list[str], timeout: float = 5.0) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _version(exe: str) -> str | None:
    if not shutil.which(exe):
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None
    # 某些构建（如 Homebrew ffmpeg 9.x）--version 退出码非 0 且输出到 stderr；
    # 只要有版本输出即视为已安装。
    text = (out.stdout or out.stderr or "").strip()
    if not text:
        return None
    return text.splitlines()[0].strip()[:120]


def _sysctl(key: str) -> str | None:
    return _run(["sysctl", "-n", key])


def _swap_gb() -> tuple[float, float, bool]:
    """解析 `sysctl -n vm.swapusage`（total = 2048.00M  used = ...）。"""
    raw = _sysctl("vm.swapusage")
    if not raw:
        return 0.0, 0.0, False

    def val(name: str) -> float:
        m = re.search(rf"{name}\s*=\s*([\d.]+)\s*([MG])", raw)
        if not m:
            return 0.0
        n = float(m.group(1))
        return n / 1024.0 if m.group(2) == "M" else n

    return val("used"), val("total"), True


def _du_gb(path) -> float | None:
    out = _run(["du", "-sk", str(path)], timeout=20)
    if out:
        try:
            return round(int(out.split()[0]) * 1024 / 1e9, 2)
        except (ValueError, IndexError):
            pass
    return None


def _check(id: str, label: str, status: str, value: str, *, detail: str = "",
           suggestion: str = "", measured: bool = True) -> dict:
    return {"id": id, "label": label, "status": status, "value": value,
            "detail": detail or None, "suggestion": suggestion or None, "measured": measured}


def _worker_alive(ws: dict) -> bool:
    pid = ws.get("pid")
    if not pid:
        return False
    try:
        import os
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def collect() -> dict:
    """完整诊断（5s 缓存）。"""
    key = (str(config.DATA_DIR), str(config.MODELS_DIR))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1]
    payload = _collect_uncached()
    _cache[key] = (time.time(), payload)
    return payload


def _collect_uncached() -> dict:
    ws = db.get_worker_state() or {}
    alive = _worker_alive(ws)
    heartbeat_fresh = bool(ws.get("heartbeat")) and (time.time() - ws["heartbeat"] < 30)

    # ---- platform ----
    chip = _sysctl("machdep.cpu.brand_string") or platform.processor() or "未知"
    arch = platform.machine()
    macos = platform.mac_ver()[0]
    metal = bool(ws.get("metal_available"))
    mlx_version = ws.get("mlx_version") or None
    versions = {
        "python": platform.python_version(),
        "uv": _version("uv"),
        "ffmpeg": _version("ffmpeg"),
        "git": _version("git"),
        "node": _version("node"),
    }

    # ---- memory ----
    total_gb = 0.0
    memsize = _sysctl("hw.memsize")
    if memsize and memsize.isdigit():
        total_gb = round(int(memsize) / 1e9, 1)
    pressure_level = audio.memory_pressure_level()
    pressure_label = PRESSURE_LABELS.get(pressure_level, "不可用")
    swap_used, swap_total, swap_measured = _swap_gb()

    # ---- disk ----
    usage = shutil.disk_usage(config.DATA_DIR if config.DATA_DIR.exists() else config.ROOT)
    disk_total = round(usage.total / 1e9, 1)
    disk_free = round(usage.free / 1e9, 1)
    models_gb = _du_gb(config.MODELS_DIR)
    data_gb = _du_gb(config.DATA_DIR)
    disk_measured = models_gb is not None and data_gb is not None
    if models_gb is None:
        # 估计回退：manifest 原始大小累计（非实际占用）
        try:
            from . import model_manager
            models_gb = round(sum(
                m.get("size", 0) for repo in model_manager.load_manifest().values() for m in repo.values()
            ) / 1e9, 2)
        except Exception:  # noqa: BLE001
            models_gb = 0.0
    if data_gb is None:
        data_gb = 0.0

    checks: list[dict] = []

    # arch
    checks.append(_check(
        "arch", "CPU 架构", "ok" if arch == "arm64" else "fail", arch,
        detail="MLX 推理需要 Apple Silicon。" if arch != "arm64" else "Apple Silicon。",
        suggestion="" if arch == "arm64" else "MLX 分支仅支持 Apple Silicon（arm64）；Intel Mac 无法使用本工作台推理。",
    ))
    # macOS
    mac_ok = True
    try:
        mac_ok = int(macos.split(".")[0]) >= 13
    except (ValueError, IndexError):
        mac_ok = False
    checks.append(_check(
        "macos", "macOS 版本", "ok" if mac_ok else "warn", macos or "未知",
        detail="MLX 需要 macOS 13+。" if not mac_ok else "",
        suggestion="" if mac_ok else "升级到 macOS 13 或更高版本以获得 MLX/Metal 支持。",
    ))
    # Metal（worker 实测心跳，不在请求里跑 GPU）
    if metal:
        metal_status, metal_detail, metal_sugg = "ok", "worker 启动时实测 Metal 可用（心跳上报，非实时采样）。", ""
    elif alive and heartbeat_fresh:
        metal_status, metal_detail, metal_sugg = "fail", "worker 报告 Metal 不可用。", "运行 ./scripts/doctor.sh 诊断；确认在 Apple Silicon 本机运行且系统未禁用 GPU。"
    else:
        metal_status, metal_detail, metal_sugg = "unknown", "worker 未上报 Metal 状态（未启动或心跳过期）。", "等待 worker 启动后刷新；若持续未知，重启后端（./scripts/stop.sh 后重新启动）。"
    checks.append(_check("metal", "Metal / MLX 后端", metal_status,
                         "可用" if metal else "不可用/未知", detail=metal_detail, suggestion=metal_sugg))
    # MLX 最小张量环境（worker 心跳：真实 import + matmul 环境）
    if mlx_version and metal:
        mlx_status, mlx_detail, mlx_sugg = "ok", f"worker 实测 MLX {mlx_version}（device={ws.get('device') or '?'}）。", ""
    elif alive and heartbeat_fresh:
        mlx_status, mlx_detail, mlx_sugg = "warn", "worker 存活但未上报 MLX 版本。", "查看 logs/worker.log；必要时重启后端。"
    else:
        mlx_status, mlx_detail, mlx_sugg = "unknown", "无 worker 心跳，无法确认 MLX 环境。", "启动后端后 worker 会自动运行最小环境检查。"
    checks.append(_check("mlx", "MLX 环境", mlx_status, mlx_version or "未知",
                         detail=mlx_detail, suggestion=mlx_sugg))
    # 内存压力
    if pressure_level == 1:
        p_status, p_sugg = "ok", ""
    elif pressure_level == 2:
        p_status, p_sugg = "warn", "关闭其他大内存应用（浏览器/IDE/虚拟机）后再提交任务。"
    elif pressure_level >= 4:
        p_status, p_sugg = "fail", "内存压力严重，推理已暂停保护系统；请关闭大内存应用后重试。"
    else:
        p_status, p_sugg = "unknown", "无法读取内存压力（sysctl 失败）；以 swap 与磁盘余量作保守参考。"
    checks.append(_check("memory_pressure", "内存压力", p_status, pressure_label,
                         detail=f"kern.memorystatus_vm_pressure_level={pressure_level}（统一内存以压力为准，不看 free RAM）。",
                         suggestion=p_sugg))
    # swap
    if not swap_measured:
        s_status, s_sugg = "unknown", "无法读取 swap 使用（sysctl vm.swapusage 失败）。"
    elif swap_total <= 0:
        s_status, s_sugg = "ok", ""
    elif swap_used > 0.5 * swap_total:
        s_status, s_sugg = "warn", "swap 使用过半，说明物理内存紧张；关闭大内存应用，必要时重启释放。"
    else:
        s_status, s_sugg = "ok", ""
    checks.append(_check("swap", "Swap 使用", s_status,
                         f"{swap_used:.1f} / {swap_total:.1f} GB" if swap_measured else "未知",
                         detail="macOS 动态 swap；大量使用会显著拖慢推理。" if swap_measured else "",
                         suggestion=s_sugg, measured=swap_measured))
    # 磁盘余量
    if disk_free >= 20:
        d_status, d_sugg = "ok", ""
    elif disk_free >= 10:
        d_status, d_sugg = "warn", "磁盘余量偏低：模型安装/转换需要 ≥20GB；清理磁盘或移走大文件。"
    else:
        d_status, d_sugg = "fail", "磁盘余量不足 10GB：无法安装/转换模型，输出也可能失败；请立即清理磁盘。"
    checks.append(_check("disk_free", "磁盘余量", d_status, f"{disk_free:.1f} GB",
                         detail="阈值：≥20GB ok / ≥10GB warn / 其余 fail。", suggestion=d_sugg))
    # 依赖工具
    for exe, label, required in (("ffmpeg", "FFmpeg", True), ("git", "Git", False), ("uv", "uv", False)):
        v = versions[exe]
        if v:
            checks.append(_check(exe, label, "ok", v))
        elif required:
            checks.append(_check(exe, label, "fail", "未安装",
                                 detail="音频解码/标准化必需。", suggestion="brew install ffmpeg"))
        else:
            checks.append(_check(exe, label, "warn", "未安装",
                                 suggestion="brew install " + exe + "（可选，用于环境管理/更新）。"))
    checks.append(_check("node", "Node.js", "ok" if versions["node"] else "unknown",
                         versions["node"] or "未安装",
                         detail="仅前端构建需要，运行已构建前端不需要。",
                         suggestion="" if versions["node"] else "如需重新构建前端：brew install node。"))
    # 模型权重完整性
    from . import model_manager
    states = {m["id"]: model_manager.model_state(m) for m in model_manager.load_registry()["models"]}
    flash_ready = states.get("auk-flash", {}).get("state") == "ready"
    all_ready = all(s.get("state") == "ready" for s in states.values())
    if all_ready:
        w_status, w_detail, w_sugg = "ok", "四个模型条目全部就绪（原始权重 + MLX 转换产物）。", ""
    elif flash_ready:
        missing = [mid for mid, s in states.items() if s.get("state") != "ready"]
        w_status, w_detail, w_sugg = "warn", f"Flash 可用；未就绪：{', '.join(missing)}。", "在模型管理页安装缺失组件（可复用已存在权重）。"
    else:
        w_status, w_detail, w_sugg = "fail", "AuK-Flash 权重不完整，无法推理。", "在模型管理页执行安装（自动探测复用，不会重复下载）。"
    checks.append(_check("model_weights", "模型权重", w_status,
                         "完整" if all_ready else ("部分" if flash_ready else "缺失"),
                         detail=w_detail, suggestion=w_sugg))
    # 磁盘占用（du 观测 vs manifest 估计）
    checks.append(_check("disk_usage", "磁盘占用", "ok",
                         f"models {models_gb:.1f} GB / data {data_gb:.1f} GB",
                         detail="du 实测。" if disk_measured else "models 为 manifest 累计估计（du 失败），data 未知。",
                         measured=disk_measured))
    # worker 存活
    if alive and heartbeat_fresh:
        wk_status, wk_detail, wk_sugg = "ok", f"pid={ws.get('pid')}，心跳 {time.time() - ws['heartbeat']:.0f}s 前。", ""
    elif alive:
        wk_status, wk_detail, wk_sugg = "warn", "进程存在但心跳过期（>30s）。", "worker 可能卡在长任务；查看 logs/worker.log，必要时重启后端。"
    else:
        wk_status, wk_detail, wk_sugg = "fail", "worker 未运行。", "重启后端：./scripts/stop.sh 后重新启动；supervisor 会自动拉起 worker。"
    checks.append(_check("worker", "推理 worker", wk_status,
                         "存活" if alive else "未运行", detail=wk_detail, suggestion=wk_sugg))

    # ---- readiness ----
    reasons: list[str] = []
    by_id = {c["id"]: c for c in checks}
    blocked = by_id["metal"]["status"] == "fail" or by_id["model_weights"]["status"] == "fail" or by_id["arch"]["status"] == "fail"
    has_unknown = any(c["status"] == "unknown" for c in checks)
    has_warn = any(c["status"] in ("warn", "fail") for c in checks)
    if blocked:
        level = "blocked"
    elif has_unknown:
        level = "unknown"
    elif has_warn or pressure_level >= 2:
        level = "caution"
    else:
        level = "ready"
    for c in checks:
        if c["status"] in ("warn", "fail", "unknown"):
            reasons.append(f"{c['label']}：{c['detail'] or c['value']}" + (f" 建议：{c['suggestion']}" if c["suggestion"] else ""))
    if level == "ready":
        reasons.append("Metal 可用、权重完整、内存压力正常、磁盘余量充足。")

    return {
        "generated_at": time.time(),
        "overall": level,
        "platform": {
            "chip": chip, "arch": arch, "macos": macos, "metal": metal,
            "mlx_version": mlx_version, **versions,
        },
        "memory": {
            "total_gb": total_gb, "pressure_level": pressure_level, "pressure_label": pressure_label,
            "swap_used_gb": round(swap_used, 2), "swap_total_gb": round(swap_total, 2),
        },
        "disk": {"total_gb": disk_total, "free_gb": disk_free,
                 "models_gb": models_gb, "data_gb": data_gb},
        "checks": checks,
        "readiness": {"level": level, "reasons": reasons},
    }


# ---------------- preflight ----------------

# 本机实测参考区间（docs/TEST_REPORT.md §2，M5 Pro/48GB）。仅允许这些基准，非承诺。
_BASELINES = {
    ("flash", 8): {"rtf_range": [0.5, 1.0], "peak_memory_gb": 7.6},
    ("flash", None): {"rtf_range": [1.26, 3.61], "peak_memory_gb": None},
    ("base", 8): {"rtf_range": [1.97, 2.21], "peak_memory_gb": 7.6},
}
_EST_NOTE = "本机实测参考（M5 Pro/48GB，docs/TEST_REPORT.md），非承诺；实际受负载、内存压力与首次 shader 编译影响。"


def preflight(model_variant: str, task: str, bits: int | None = None, sequential: bool = False) -> dict:
    from . import model_manager

    # task 允许传能力键或 mode
    task_key = capabilities.TASK_BY_MODE.get(task, task)
    entry = capabilities.task_entry(task_key)

    reasons: list[str] = []
    level = "ready"

    def downgrade(to: str, reason: str) -> None:
        nonlocal level
        order = {"ready": 0, "unknown": 1, "caution": 2, "blocked": 3}
        if order[to] > order[level]:
            level = to
        reasons.append(reason)

    model_id = "auk-flash" if model_variant == "flash" else "auk-base"
    registry = model_manager.load_registry()
    entry_m = next(m for m in registry["models"] if m["id"] == model_id)
    state = model_manager.model_state(entry_m)
    deps_ok = True
    for dep in entry_m.get("depends_on", []):
        dep_m = next(m for m in registry["models"] if m["id"] == dep)
        if model_manager.model_state(dep_m)["state"] != "ready":
            deps_ok = False
    if state["state"] != "ready" or not deps_ok:
        downgrade("blocked", f"模型 {model_id} 或其依赖未就绪（{state['state']}）；请先在模型管理页安装。")
    else:
        reasons.append(f"模型 {model_id} 及依赖已就绪。")

    cap_state = entry.get("state", "unverified")
    if cap_state == "not_supported":
        downgrade("blocked", f"任务 {task_key} 不支持：{entry.get('note') or 'MLX 分支未实现。'}")
    elif cap_state == "unverified":
        downgrade("caution", f"任务 {task_key} 为实验性（未客观验证），可试用但不承诺效果。")

    pressure = audio.memory_pressure_level()
    if pressure >= 4:
        downgrade("blocked", "内存压力严重（level≥4），推理护栏将暂停任务；请关闭大内存应用。")
    elif pressure == 2:
        downgrade("caution", "内存压力偏高（level=2），推理可能变慢或触发 swap。")

    usage = shutil.disk_usage(config.DATA_DIR if config.DATA_DIR.exists() else config.ROOT)
    free_gb = round(usage.free / 1e9, 1)
    if free_gb < 10:
        downgrade("caution", f"磁盘余量 {free_gb}GB 偏低（<10GB），输出/临时文件可能失败。")

    ws = db.get_worker_state() or {}
    queue_length = db.count_active_jobs()
    if queue_length >= 3:
        downgrade("caution", f"队列中已有 {queue_length} 个任务，新任务需排队等待。")
    if not _worker_alive(ws):
        downgrade("caution", "worker 当前未运行；提交任务后 supervisor 会自动拉起（首个任务含加载耗时）。")

    model_loaded = bool(ws.get("model_loaded")) and ws.get("model_variant") == model_variant
    if model_loaded:
        reasons.append("模型已常驻，任务将复用引擎（无加载耗时）。")

    baseline = _BASELINES.get((model_variant, bits))
    estimates = {
        "peak_memory_gb": baseline["peak_memory_gb"] if baseline else None,
        "rtf_range": baseline["rtf_range"] if baseline else None,
        "note": _EST_NOTE if baseline else "该配置无本机实测基准，不提供估计（非承诺）。",
    }
    if sequential:
        reasons.append("sequential 模式峰值内存更低、速度略慢（8-bit 下输出与并行 bit-identical）。")

    return {
        "level": level,
        "reasons": reasons,
        "model_loaded": model_loaded,
        "queue_length": queue_length,
        "disk_free_gb": free_gb,
        "estimates": estimates,
    }