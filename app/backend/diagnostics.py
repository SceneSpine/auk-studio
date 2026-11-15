"""系统资源探针与运行前评估（docs/API_CONTRACT.md §diagnostics/preflight）。

原则：
- 真实探针：macOS sysctl / Linux /proc（meminfo/loadavg/cpuinfo/os-release）/
  Windows GlobalMemoryStatusEx + win32_ver；观测值与估计值用 measured 区分。
- Apple 统一内存不能只看 free RAM：结合内存压力、swap、模型峰值经验。
- 不在 HTTP 请求里跑 GPU：MLX/Metal 状态取 worker 心跳（worker 启动时真实导入并运行）。
- 不伪造 GPU 占用百分比。
- 跨平台：本地推理仅 Apple Silicon + MLX；其余平台探针不可得 → measured=false/unknown，
  绝不抛异常。readiness：非 Mac 且无启用的远程 provider → blocked（指引配置远程）。
- 结果缓存 5s，避免重复 subprocess。
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import audio, capabilities, config, db, providers

CACHE_TTL_S = 5.0
_cache: dict[tuple, tuple[float, dict]] = {}

PRESSURE_LABELS = {1: "正常", 2: "偏高", 4: "严重"}

# 非 Mac 平台的统一指引（本地推理仅 Apple Silicon）
_REMOTE_SUGGESTION = "在模型管理页配置远程 AuK 服务或 HuggingFace Space，使用远程任务推理。"
_LOCAL_ONLY_DETAIL = "本地推理需 Apple Silicon（macOS + MLX）；此平台可通过远程 provider 推理。"


def _run(cmd: list[str], timeout: float = 5.0) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
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


def _disk_usage_gb(path) -> tuple[float, float]:
    """磁盘总量/余量（GB）。shutil.disk_usage 跨平台；失败回退 df（POSIX）。"""
    try:
        usage = shutil.disk_usage(path)
        return round(usage.total / 1e9, 1), round(usage.free / 1e9, 1)
    except OSError:
        pass
    out = _run(["df", "-Pk", str(path)])
    if out:
        try:
            fields = out.splitlines()[-1].split()
            return round(int(fields[1]) * 1024 / 1e9, 1), round(int(fields[3]) * 1024 / 1e9, 1)
        except (ValueError, IndexError):
            pass
    return 0.0, 0.0


def _check(id: str, label: str, status: str, value: str, *, detail: str = "",
           suggestion: str = "", measured: bool = True) -> dict:
    return {"id": id, "label": label, "status": status, "value": value,
            "detail": detail or None, "suggestion": suggestion or None, "measured": measured}


def pid_alive(pid) -> bool:
    """跨平台进程存活检查。

    POSIX：os.kill(pid, 0)。Windows：os.kill(pid, 0) 会无条件终止进程，
    必须改用 OpenProcess 查询（PROCESS_QUERY_LIMITED_INFORMATION）。
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except Exception:  # noqa: BLE001 - 探针绝不抛异常
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _worker_alive(ws: dict) -> bool:
    return pid_alive(ws.get("pid"))


# ---------------- 平台感知资源探针 ----------------

def _probe_macos() -> dict:
    """macOS：sysctl 探针（行为与跨平台改造前完全一致）。"""
    chip = _sysctl("machdep.cpu.brand_string") or platform.processor() or "未知"
    total_gb, mem_measured = 0.0, False
    memsize = _sysctl("hw.memsize")
    if memsize and memsize.isdigit():
        total_gb = round(int(memsize) / 1e9, 1)
        mem_measured = True
    swap_used, swap_total, swap_measured = _swap_gb()
    return {
        "chip": chip, "os_version": platform.mac_ver()[0],
        "total_gb": total_gb, "mem_measured": mem_measured,
        "swap_used_gb": swap_used, "swap_total_gb": swap_total, "swap_measured": swap_measured,
        "pressure_level": audio.memory_pressure_level(),
        "loadavg": None, "mem_load_pct": None,
    }


def _parse_meminfo(text: str) -> dict[str, int]:
    """/proc/meminfo → {key: kB}（如 MemTotal/SwapTotal/SwapFree）。"""
    out: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            try:
                out[parts[0][:-1]] = int(parts[1])
            except ValueError:
                pass
    return out


def _linux_os_release() -> str:
    """发行版名称：platform.freedesktop_os_release 优先，回退 /etc/os-release。"""
    try:
        info = platform.freedesktop_os_release()
        name = info.get("PRETTY_NAME") or info.get("NAME") or ""
        if name:
            return name
    except (OSError, AttributeError):
        pass
    raw = _read_text("/etc/os-release")
    if raw:
        fields = {}
        for line in raw.splitlines():
            k, _, v = line.partition("=")
            fields[k.strip()] = v.strip().strip('"')
        return fields.get("PRETTY_NAME") or fields.get("NAME") or ""
    return ""


def _probe_linux() -> dict:
    """Linux：/proc/meminfo、/proc/loadavg、/proc/cpuinfo、os-release。不可得 → 降级。"""
    chip = platform.processor() or "未知"
    cpuinfo = _read_text("/proc/cpuinfo")
    if cpuinfo:
        m = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
        if m:
            chip = m.group(1).strip()
    total_gb, mem_measured = 0.0, False
    swap_used = swap_total = 0.0
    swap_measured = False
    meminfo = _read_text("/proc/meminfo")
    if meminfo:
        info = _parse_meminfo(meminfo)
        if "MemTotal" in info:
            total_gb = round(info["MemTotal"] * 1024 / 1e9, 1)
            mem_measured = True
        if "SwapTotal" in info:
            swap_total = round(info["SwapTotal"] * 1024 / 1e9, 2)
            swap_used = round(max(0, info["SwapTotal"] - info.get("SwapFree", 0)) * 1024 / 1e9, 2)
            swap_measured = True
    loadavg = None
    raw = _read_text("/proc/loadavg")
    if raw:
        try:
            loadavg = [float(x) for x in raw.split()[:3]]
        except ValueError:
            pass
    return {
        "chip": chip, "os_version": _linux_os_release(),
        "total_gb": total_gb, "mem_measured": mem_measured,
        "swap_used_gb": swap_used, "swap_total_gb": swap_total, "swap_measured": swap_measured,
        "pressure_level": 0,  # macOS 专属指标；Linux 以 loadavg/swap 作保守参考
        "loadavg": loadavg, "mem_load_pct": None,
    }


def _windows_memory() -> tuple[float, int | None, bool]:
    """GlobalMemoryStatusEx → (total_gb, 内存使用率%, measured)。不可得 → (0, None, False)。"""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        windll = getattr(ctypes, "windll", None)  # 仅 Windows 存在
        if windll is None:
            return 0.0, None, False
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return 0.0, None, False
        return round(stat.ullTotalPhys / 1e9, 1), int(stat.dwMemoryLoad), True
    except Exception:  # noqa: BLE001 - 探针绝不抛异常
        return 0.0, None, False


def _probe_windows() -> dict:
    """Windows：GlobalMemoryStatusEx（内存）+ platform.win32_ver（版本）。"""
    release, version, _csd, _ptype = platform.win32_ver()
    os_version = f"Windows {release} ({version})" if release and version else (
        f"Windows {release}" if release else "")
    total_gb, load_pct, measured = _windows_memory()
    return {
        "chip": platform.processor() or "未知", "os_version": os_version,
        "total_gb": total_gb, "mem_measured": measured,
        # Windows 页面文件与 macOS swap 语义不同，不作等价观测 → unknown
        "swap_used_gb": 0.0, "swap_total_gb": 0.0, "swap_measured": False,
        "pressure_level": 0, "loadavg": None, "mem_load_pct": load_pct,
    }


def _platform_probe() -> dict:
    """按平台分发资源探针；任何字段不可得 → 0/None/measured=False，绝不抛异常。"""
    system = platform.system()
    if system == "Darwin":
        facts = _probe_macos()
    elif system == "Linux":
        facts = _probe_linux()
    elif system == "Windows":
        facts = _probe_windows()
    else:  # 未知平台：保守降级
        facts = {
            "chip": platform.processor() or "未知", "os_version": "",
            "total_gb": 0.0, "mem_measured": False,
            "swap_used_gb": 0.0, "swap_total_gb": 0.0, "swap_measured": False,
            "pressure_level": 0, "loadavg": None, "mem_load_pct": None,
        }
    facts["system"] = system
    facts["arch"] = platform.machine()
    facts["macos"] = platform.mac_ver()[0] if system == "Darwin" else ""
    return facts


def memory_total_gb() -> float:
    """物理内存总量（GB），跨平台；不可得 → 0.0。供 /api/system 使用。"""
    return _platform_probe()["total_gb"]


def _has_enabled_remote() -> bool:
    """providers 表是否有启用的远程 provider（auk_remote / hf_space）。"""
    try:
        row = db.one(db.connect().execute(
            "SELECT COUNT(*) AS n FROM providers WHERE enabled=1 AND kind IN (?, ?)",
            (providers.KIND, providers.KIND_HF_SPACE)))
        return bool(row and row["n"] > 0)
    except Exception:  # noqa: BLE001 - 表缺失等异常 → 保守视为无
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

    # ---- platform（平台感知探针）----
    facts = _platform_probe()
    is_mac = facts["system"] == "Darwin"
    chip = facts["chip"]
    arch = facts["arch"]
    macos = facts["macos"]
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
    total_gb = facts["total_gb"]
    pressure_level = facts["pressure_level"]
    pressure_label = PRESSURE_LABELS.get(pressure_level, "不可用")
    swap_used, swap_total, swap_measured = (
        facts["swap_used_gb"], facts["swap_total_gb"], facts["swap_measured"])

    # ---- disk ----
    disk_total, disk_free = _disk_usage_gb(config.DATA_DIR if config.DATA_DIR.exists() else config.ROOT)
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
    if is_mac:
        checks.append(_check(
            "arch", "CPU 架构", "ok" if arch == "arm64" else "fail", arch,
            detail="MLX 推理需要 Apple Silicon。" if arch != "arm64" else "Apple Silicon。",
            suggestion="" if arch == "arm64" else "MLX 分支仅支持 Apple Silicon（arm64）；Intel Mac 无法使用本工作台推理。",
        ))
    else:
        checks.append(_check(
            "arch", "CPU 架构", "ok", arch,
            detail=_LOCAL_ONLY_DETAIL,
        ))
    # 操作系统（macOS 版本 / Linux 发行版 / Windows 版本）
    if is_mac:
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
    else:
        checks.append(_check(
            "macos", "操作系统", "ok", facts["os_version"] or "未知",
            detail=_LOCAL_ONLY_DETAIL, measured=bool(facts["os_version"]),
        ))
    # Metal（worker 实测心跳，不在请求里跑 GPU）
    if not is_mac:
        checks.append(_check(
            "metal", "Metal / MLX 后端", "warn", "不可用（非 Apple 平台）",
            detail="Metal 为 Apple 平台专属；此平台无法本地推理。",
            suggestion=_REMOTE_SUGGESTION, measured=False,
        ))
    elif metal:
        metal_status, metal_detail, metal_sugg = "ok", "worker 启动时实测 Metal 可用（心跳上报，非实时采样）。", ""
        checks.append(_check("metal", "Metal / MLX 后端", metal_status, "可用",
                             detail=metal_detail, suggestion=metal_sugg))
    elif alive and heartbeat_fresh:
        metal_status, metal_detail, metal_sugg = "fail", "worker 报告 Metal 不可用。", "运行 ./scripts/doctor.sh 诊断；确认在 Apple Silicon 本机运行且系统未禁用 GPU。"
        checks.append(_check("metal", "Metal / MLX 后端", metal_status, "不可用/未知",
                             detail=metal_detail, suggestion=metal_sugg))
    else:
        metal_status, metal_detail, metal_sugg = "unknown", "worker 未上报 Metal 状态（未启动或心跳过期）。", "等待 worker 启动后刷新；若持续未知，重启后端（./scripts/stop.sh 后重新启动）。"
        checks.append(_check("metal", "Metal / MLX 后端", metal_status, "不可用/未知",
                             detail=metal_detail, suggestion=metal_sugg))
    # MLX 最小张量环境（worker 心跳：真实 import + matmul 环境）
    if not is_mac:
        checks.append(_check(
            "mlx", "MLX 环境", "warn", mlx_version or "不可用",
            detail="worker 探针：MLX 不可用（mlx_available=0）；此平台不支持本地推理。",
            suggestion=_REMOTE_SUGGESTION, measured=False,
        ))
    elif mlx_version and metal:
        mlx_status, mlx_detail, mlx_sugg = "ok", f"worker 实测 MLX {mlx_version}（device={ws.get('device') or '?'}）。", ""
        checks.append(_check("mlx", "MLX 环境", mlx_status, mlx_version,
                             detail=mlx_detail, suggestion=mlx_sugg))
    elif alive and heartbeat_fresh:
        mlx_status, mlx_detail, mlx_sugg = "warn", "worker 存活但未上报 MLX 版本。", "查看 logs/worker.log；必要时重启后端。"
        checks.append(_check("mlx", "MLX 环境", mlx_status, "未知",
                             detail=mlx_detail, suggestion=mlx_sugg))
    else:
        mlx_status, mlx_detail, mlx_sugg = "unknown", "无 worker 心跳，无法确认 MLX 环境。", "启动后端后 worker 会自动运行最小环境检查。"
        checks.append(_check("mlx", "MLX 环境", mlx_status, "未知",
                             detail=mlx_detail, suggestion=mlx_sugg))
    # 内存压力（macOS 专属指标；其余平台 unknown，以 swap/磁盘余量作保守参考）
    if not is_mac:
        p_detail = "内存压力探针仅 macOS 可用；此平台以 swap 与磁盘余量作保守参考。"
        if facts["loadavg"]:
            p_detail += " loadavg(1/5/15min)=" + "/".join(f"{v:.2f}" for v in facts["loadavg"]) + "。"
        if facts["mem_load_pct"] is not None:
            p_detail += f" 内存使用率 {facts['mem_load_pct']}%。"
        checks.append(_check("memory_pressure", "内存压力", "unknown", "不可用",
                             detail=p_detail, measured=False))
    else:
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
        s_status, s_sugg = "unknown", ("无法读取 swap 使用（sysctl vm.swapusage 失败）。" if is_mac
                                       else "此平台 swap 探针不可用；以磁盘余量作保守参考。")
    elif swap_total <= 0:
        s_status, s_sugg = "ok", ""
    elif swap_used > 0.5 * swap_total:
        s_status, s_sugg = "warn", "swap 使用过半，说明物理内存紧张；关闭大内存应用，必要时重启释放。"
    else:
        s_status, s_sugg = "ok", ""
    swap_detail = ""
    if swap_measured:
        swap_detail = ("macOS 动态 swap；大量使用会显著拖慢推理。" if is_mac
                       else "swap 大量使用会显著拖慢推理。")
    checks.append(_check("swap", "Swap 使用", s_status,
                         f"{swap_used:.1f} / {swap_total:.1f} GB" if swap_measured else "未知",
                         detail=swap_detail, suggestion=s_sugg, measured=swap_measured))
    # 磁盘余量
    if disk_free >= 20:
        d_status, d_sugg = "ok", ""
    elif disk_free >= 10:
        d_status, d_sugg = "warn", "磁盘余量偏低：模型安装/转换需要 ≥20GB；清理磁盘或移走大文件。"
    else:
        d_status, d_sugg = "fail", "磁盘余量不足 10GB：无法安装/转换模型，输出也可能失败；请立即清理磁盘。"
    checks.append(_check("disk_free", "磁盘余量", d_status, f"{disk_free:.1f} GB",
                         detail="阈值：≥20GB ok / ≥10GB warn / 其余 fail。", suggestion=d_sugg))
    # 依赖工具（安装建议按平台区分）
    def _install_hint(exe: str) -> str:
        if is_mac:
            return "brew install " + exe
        if facts["system"] == "Linux":
            return f"请使用系统包管理器安装 {exe}（如 apt install {exe}）。"
        return f"请安装 {exe} 并加入 PATH。"

    for exe, label, required in (("ffmpeg", "FFmpeg", True), ("git", "Git", False), ("uv", "uv", False)):
        v = versions[exe]
        if v:
            checks.append(_check(exe, label, "ok", v))
        elif required:
            checks.append(_check(exe, label, "fail", "未安装",
                                 detail="音频解码/标准化必需。", suggestion=_install_hint(exe)))
        else:
            checks.append(_check(exe, label, "warn", "未安装",
                                 suggestion=_install_hint(exe) + "（可选，用于环境管理/更新）。"))
    checks.append(_check("node", "Node.js", "ok" if versions["node"] else "unknown",
                         versions["node"] or "未安装",
                         detail="仅前端构建需要，运行已构建前端不需要。",
                         suggestion="" if versions["node"] else (
                             "如需重新构建前端：brew install node。" if is_mac else "如需重新构建前端：请安装 Node.js。")))
    # 模型权重完整性（非 Mac：权重仅本地推理需要，缺失不 fail，远程任务不受影响）
    from . import model_manager
    states = {m["id"]: model_manager.model_state(m) for m in model_manager.load_registry()["models"]}
    flash_ready = states.get("auk-flash", {}).get("state") == "ready"
    all_ready = all(s.get("state") == "ready" for s in states.values())
    if all_ready:
        w_status, w_detail, w_sugg = "ok", "四个模型条目全部就绪（原始权重 + MLX 转换产物）。", ""
    elif not is_mac:
        w_status = "warn"
        w_detail = "本地权重不完整；此平台本地推理不可用（需 Apple Silicon），远程任务不受影响。"
        w_sugg = _REMOTE_SUGGESTION
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
    if not is_mac:
        # 非 Mac：本地推理需 Apple Silicon；有启用的远程 provider 时远程任务可正常运行
        if not _has_enabled_remote():
            level = "blocked"
            reasons.append("本地推理需 Apple Silicon（macOS + MLX）；此平台未配置启用的远程 provider。"
                           "请在模型管理页配置远程 AuK 服务或 HuggingFace Space 后使用远程任务。")
        else:
            level = "blocked" if any(c["status"] == "fail" for c in checks) else "caution"
            reasons.append("此平台非 Apple Silicon：本地推理不可用；已配置启用的远程 provider，远程任务可正常运行。")
    else:
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

    platform_payload = {
        "chip": chip, "arch": arch, "macos": macos, "metal": metal,
        "mlx_version": mlx_version, **versions,
        # 跨平台附加字段（extra=allow，前端按 types.ts 消费既有字段）
        "system": facts["system"], "os": facts["os_version"],
        "mlx_available": bool(ws.get("mlx_available")),
    }
    if facts["loadavg"] is not None:
        platform_payload["loadavg"] = facts["loadavg"]
    if facts["mem_load_pct"] is not None:
        platform_payload["memory_load_pct"] = facts["mem_load_pct"]

    return {
        "generated_at": time.time(),
        "overall": level,
        "platform": platform_payload,
        "memory": {
            "total_gb": total_gb, "pressure_level": pressure_level, "pressure_label": pressure_label,
            "swap_used_gb": round(swap_used, 2), "swap_total_gb": round(swap_total, 2),
            "measured": facts["mem_measured"],
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

    if platform.system() != "Darwin":
        downgrade("blocked", "此平台不支持本地推理（需 Apple Silicon + MLX）；"
                             "请在模型管理页配置远程 AuK 服务或 HuggingFace Space，使用远程任务。")

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
