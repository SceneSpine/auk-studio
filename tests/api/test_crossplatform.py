"""跨平台工作台：MLX 懒加载 / 本地任务门禁 / 远程任务不受影响 / 诊断平台探针 / 迁移。

非 Mac 行为用 mock 模拟（import mlx 失败、platform.system()="Linux"/"Windows"），
本机 Mac 真实路径不变；不启动真实 worker、不加载模型、不触外网（远程用 mock_auk/mock_gradio）。
"""
from __future__ import annotations

import asyncio
import builtins
import os
import signal
import sqlite3
import subprocess
import sys
import types

import pytest

from app.backend import audio, config, db, diagnostics, worker
from app.backend import main as backend_main

from mock_auk import mock_auk
from mock_gradio import mock_gradio


# ---------------- fixtures / helpers ----------------

@pytest.fixture()
def no_mlx(monkeypatch):
    """mock import mlx 失败（模拟非 Apple Silicon 平台 / MLX 依赖缺失）。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mlx" or name.startswith("mlx."):
            raise ImportError("No module named 'mlx' (mock: 非 Mac 平台)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


@pytest.fixture()
def fake_mlx(monkeypatch):
    """注入假 mlx.core（探针成功分支；不依赖真实 MLX，任何平台可跑）。"""
    pkg = types.ModuleType("mlx")
    core = types.ModuleType("mlx.core")
    core.__version__ = "0.0-fake"
    core.default_device = lambda: "fake_device"
    core.metal = types.SimpleNamespace(is_available=lambda: True)
    pkg.core = core
    monkeypatch.setitem(sys.modules, "mlx", pkg)
    monkeypatch.setitem(sys.modules, "mlx.core", core)
    return core


@pytest.fixture()
def fresh_diag_cache(monkeypatch):
    """诊断 5s 缓存隔离：避免跨用例命中缓存。"""
    monkeypatch.setattr(diagnostics, "_cache", {})


def _mock_system(monkeypatch, name: str) -> None:
    monkeypatch.setattr(diagnostics.platform, "system", lambda: name)


def _alive_worker_heartbeat() -> None:
    """把 worker 心跳设为当前（存活的）pytest 进程，使 worker 检查项为 ok。"""
    db.worker_heartbeat(os.getpid())


def _assert_diag_structure(j: dict) -> None:
    assert j["platform"]["python"]
    assert j["platform"]["arch"]
    assert isinstance(j["memory"]["total_gb"], float)
    assert j["memory"]["pressure_label"] in ("正常", "偏高", "严重", "不可用")
    assert j["disk"]["total_gb"] > 0
    assert j["readiness"]["level"] in ("ready", "caution", "blocked", "unknown")
    assert j["overall"] == j["readiness"]["level"]
    ids = {c["id"] for c in j["checks"]}
    for required in ("arch", "macos", "metal", "mlx", "memory_pressure", "swap",
                     "disk_free", "ffmpeg", "git", "uv", "node", "model_weights",
                     "disk_usage", "worker"):
        assert required in ids, f"缺少检查项 {required}"
    for c in j["checks"]:
        assert c["status"] in ("ok", "warn", "fail", "unknown")
        assert isinstance(c["measured"], bool)
        if c["status"] in ("warn", "fail"):
            assert c["suggestion"], f"{c['id']} 缺少 suggestion"


def _clear_providers(client) -> None:
    for p in client.get("/api/providers").json()["providers"]:
        client.delete(f"/api/providers/{p['id']}")


# ---------------- worker：MLX 懒加载探针 ----------------

def test_probe_mlx_failure_does_not_exit(client, no_mlx):
    """import mlx 失败 → 探针返回 False（不 sys.exit），心跳 mlx_available=0 + last_error。"""
    assert worker._probe_mlx(os.getpid()) is False
    ws = db.get_worker_state()
    assert ws["mlx_available"] == 0
    assert "MLX" in ws["last_error"]


def test_probe_mlx_success_reports_available(client, fake_mlx):
    assert worker._probe_mlx(os.getpid()) is True
    ws = db.get_worker_state()
    assert ws["mlx_available"] == 1
    assert ws["mlx_version"] == "0.0-fake"
    assert ws["metal_available"] == 1
    assert ws["device"] == "fake_device"


def test_worker_main_starts_without_mlx(client, no_mlx, monkeypatch):
    """main() 在无 MLX 平台正常启动并进入任务循环（不退出）；探针说明保留在 last_error。"""
    db.consume_unload_request()
    db.consume_activate_request()

    def stop_loop(pid):
        raise KeyboardInterrupt  # 首轮循环即优雅退出

    monkeypatch.setattr(db, "claim_next_job", stop_loop)
    worker.main()  # 不应抛 SystemExit
    ws = db.get_worker_state()
    assert ws["mlx_available"] == 0
    assert "MLX" in ws["last_error"]


def test_worker_state_has_mlx_available(client):
    """新建库 SCHEMA 即含 mlx_available 列。"""
    assert "mlx_available" in db.get_worker_state()


# ---------------- worker：本地门禁 / 远程不受影响 ----------------

def test_local_job_failed_without_mlx(client, audio, no_mlx):
    r = client.post("/api/jobs", json={
        "audio_id": audio["id"], "mode": "replace",
        "segment": {"original": "会议室", "replacement": "发布会"},
    })
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    holder = worker.EngineHolder()
    worker.run_job(db.get_job(jid), holder)
    done = db.get_job(jid)
    assert done["status"] == "failed"
    assert "此平台不支持本地推理" in done["error"]
    assert "Apple Silicon" in done["error"]
    assert "远程" in done["error"]
    assert holder.engine is None  # 未尝试加载模型
    assert done["output_path"] is None


def test_local_gate_before_input_validation(client, no_mlx):
    """门禁在输入校验之前：无音频的本地任务也报平台不支持（而非“原始音频不存在”）。"""
    job = db.insert_job({"audio_id": None, "mode": "replace",
                         "segment_json": {"original": "a", "replacement": "b"}})
    worker.run_job(db.get_job(job["id"]), worker.EngineHolder())
    done = db.get_job(job["id"])
    assert done["status"] == "failed"
    assert "此平台不支持本地推理" in done["error"]


def test_remote_auk_job_unaffected_without_mlx(client, audio, no_mlx):
    with mock_auk(wav_seconds=0.6) as srv:
        p = client.post("/api/providers", json={
            "name": "远程 AuK", "kind": "auk_remote", "base_url": srv.base_url}).json()
        r = client.post("/api/jobs", json={
            "provider_id": p["id"], "mode": "replace", "audio_id": audio["id"],
            "segment": {"original": "会议室", "replacement": "发布会"}})
        assert r.status_code == 200, r.text
        jid = r.json()["id"]
        holder = worker.EngineHolder()
        worker.run_job(db.get_job(jid), holder)  # 路由入口：远程分支不碰 MLX
        done = db.get_job(jid)
        assert done["status"] == "completed", done["error"]
        assert holder.engine is None
        assert done["rtf"] is None and done["peak_memory_gb"] is None
        client.delete(f"/api/providers/{p['id']}")


def test_hf_space_job_unaffected_without_mlx(client, audio, no_mlx):
    with mock_gradio(wav_seconds=0.6) as srv:
        p = client.post("/api/providers", json={
            "name": "HF Space", "kind": "hf_space", "base_url": srv.base_url}).json()
        r = client.post("/api/jobs", json={
            "provider_id": p["id"], "mode": "replace", "audio_id": audio["id"],
            "segment": {"original": "会议室", "replacement": "发布会"}})
        assert r.status_code == 200, r.text
        jid = r.json()["id"]
        holder = worker.EngineHolder()
        worker.run_job(db.get_job(jid), holder)
        done = db.get_job(jid)
        assert done["status"] == "completed", done["error"]
        assert holder.engine is None
        client.delete(f"/api/providers/{p['id']}")


def test_verify_job_unaffected_without_mlx(client, tiny_model_env, no_mlx):
    """模型管理（install/verify）不需要 MLX，非 Mac 平台照常工作。"""
    job = db.insert_job({"audio_id": None, "mode": "verify", "kind": "verify", "model_id": "tiny"})
    worker.run_job(db.get_job(job["id"]), worker.EngineHolder())
    assert db.get_job(job["id"])["status"] == "completed"


# ---------------- diagnostics：平台感知 ----------------

def test_diagnostics_linux_structure(client, fresh_diag_cache, monkeypatch):
    """mock Linux：结构完整不抛异常；宿主无 /proc 时降级为 unknown/measured=False。"""
    _mock_system(monkeypatch, "Linux")
    _alive_worker_heartbeat()
    j = diagnostics.collect()
    _assert_diag_structure(j)
    assert j["platform"]["system"] == "Linux"
    assert j["platform"]["macos"] == ""
    assert j["memory"]["pressure_level"] == 0
    if sys.platform != "linux":  # Mac/Windows 宿主无 /proc → 探针降级
        assert j["memory"]["total_gb"] == 0.0
        assert j["memory"]["measured"] is False
        swap = next(c for c in j["checks"] if c["id"] == "swap")
        assert swap["measured"] is False and swap["status"] == "unknown"
        mp = next(c for c in j["checks"] if c["id"] == "memory_pressure")
        assert mp["status"] == "unknown" and mp["measured"] is False


def test_diagnostics_linux_proc_parsing(client, fresh_diag_cache, monkeypatch):
    """Linux 探针解析：/proc/meminfo、/proc/loadavg、/proc/cpuinfo、os-release。"""
    _mock_system(monkeypatch, "Linux")
    files = {
        "/proc/meminfo": ("MemTotal:       16384000 kB\nMemFree:        100 kB\n"
                          "SwapTotal:       4194304 kB\nSwapFree:        1048576 kB\n"),
        "/proc/loadavg": "0.52 0.58 0.59 1/435 12345\n",
        "/proc/cpuinfo": "processor\t: 0\nmodel name\t: Fake CPU X\n",
        "/etc/os-release": 'PRETTY_NAME="Ubuntu 24.04 LTS"\nNAME="Ubuntu"\n',
    }
    monkeypatch.setattr(diagnostics, "_read_text", lambda p: files.get(p))
    monkeypatch.setattr(diagnostics.platform, "freedesktop_os_release",
                        lambda: {"PRETTY_NAME": "Ubuntu 24.04 LTS"})
    _alive_worker_heartbeat()
    j = diagnostics.collect()
    _assert_diag_structure(j)
    assert j["platform"]["chip"] == "Fake CPU X"
    assert j["platform"]["os"] == "Ubuntu 24.04 LTS"
    assert j["memory"]["total_gb"] == round(16384000 * 1024 / 1e9, 1)
    assert j["memory"]["measured"] is True
    assert j["memory"]["swap_total_gb"] == round(4194304 * 1024 / 1e9, 2)
    assert j["memory"]["swap_used_gb"] == round((4194304 - 1048576) * 1024 / 1e9, 2)
    assert j["platform"]["loadavg"] == [0.52, 0.58, 0.59]
    swap = next(c for c in j["checks"] if c["id"] == "swap")
    assert swap["measured"] is True


def test_diagnostics_windows_structure(client, fresh_diag_cache, monkeypatch):
    """mock Windows：结构完整不抛异常；非 Windows 宿主无 windll → 内存降级。"""
    _mock_system(monkeypatch, "Windows")
    _alive_worker_heartbeat()
    j = diagnostics.collect()
    _assert_diag_structure(j)
    assert j["platform"]["system"] == "Windows"
    assert j["memory"]["pressure_level"] == 0
    if os.name != "nt":
        assert j["memory"]["measured"] is False
        assert j["memory"]["total_gb"] == 0.0


def test_diagnostics_windows_memory_probe(client, fresh_diag_cache, monkeypatch):
    """GlobalMemoryStatusEx 解析（fake kernel32 填充结构体，任何平台可跑）。"""
    _mock_system(monkeypatch, "Windows")
    monkeypatch.setattr(diagnostics.platform, "win32_ver",
                        lambda: ("10", "10.0.19045", "SP0", "Multiprocessor Free"))

    class FakeKernel32:
        @staticmethod
        def GlobalMemoryStatusEx(ptr):
            stat = ptr._obj  # ctypes.byref → CArgObject
            stat.ullTotalPhys = 32 * 10**9
            stat.dwMemoryLoad = 42
            return 1

    monkeypatch.setattr(diagnostics.ctypes, "windll",
                        types.SimpleNamespace(kernel32=FakeKernel32), raising=False)
    _alive_worker_heartbeat()
    j = diagnostics.collect()
    _assert_diag_structure(j)
    assert j["memory"]["total_gb"] == 32.0
    assert j["memory"]["measured"] is True
    assert j["platform"]["memory_load_pct"] == 42
    assert j["platform"]["os"] == "Windows 10 (10.0.19045)"


# ---------------- readiness：非 Mac + 远程 provider ----------------

def test_readiness_non_mac_no_remote_blocked(client, fresh_diag_cache, monkeypatch):
    _mock_system(monkeypatch, "Linux")
    _alive_worker_heartbeat()
    _clear_providers(client)
    j = diagnostics.collect()
    assert j["readiness"]["level"] == "blocked"
    assert any("Apple Silicon" in r and "远程" in r for r in j["readiness"]["reasons"])


def test_readiness_non_mac_with_remote(client, fresh_diag_cache, monkeypatch):
    _mock_system(monkeypatch, "Linux")
    _alive_worker_heartbeat()
    _clear_providers(client)
    p = client.post("/api/providers", json={
        "name": "远程 AuK", "kind": "auk_remote", "base_url": "https://auk.example.com"}).json()
    j = diagnostics.collect()
    assert j["readiness"]["level"] in ("caution", "ready")
    assert any("远程 provider" in r for r in j["readiness"]["reasons"])
    # 停用的 provider 不算可用远程 → 回到 blocked
    client.put(f"/api/providers/{p['id']}", json={"enabled": False})
    diagnostics._cache.clear()
    j2 = diagnostics.collect()
    assert j2["readiness"]["level"] == "blocked"
    client.delete(f"/api/providers/{p['id']}")


def test_preflight_non_mac_blocked(client, monkeypatch):
    _mock_system(monkeypatch, "Linux")
    j = client.post("/api/system/preflight", json={
        "model_variant": "flash", "task": "speech_edit", "bits": 8}).json()
    assert j["level"] == "blocked"
    assert any("Apple Silicon" in r for r in j["reasons"])


def test_system_endpoint_non_mac(client, fresh_diag_cache, monkeypatch):
    """/api/system 不再直接跑 sysctl：mock Linux/Windows 下 200 且结构完整。"""
    for name in ("Linux", "Windows"):
        _mock_system(monkeypatch, name)
        r = client.get("/api/system")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["platform"]["system"] == name
        assert isinstance(j["memory"]["total_gb"], float)
        assert "worker" in j and "paths" in j


# ---------------- audio：非 macOS 内存压力 ----------------

@pytest.mark.parametrize("plat", ["linux", "win32"])
def test_memory_pressure_non_macos(monkeypatch, plat):
    monkeypatch.setattr(audio.sys, "platform", plat)
    assert audio.memory_pressure_level() == 0


# ---------------- main.py：supervisor 信号兼容 ----------------

def _dummy_proc() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _spy_signals(monkeypatch, proc: subprocess.Popen) -> list:
    sent: list = []
    orig = proc.send_signal

    def spy(sig):
        sent.append(sig)
        orig(sig)

    monkeypatch.setattr(proc, "send_signal", spy)
    return sent


def test_supervisor_stop_windows_uses_terminate(monkeypatch):
    sup = backend_main.WorkerSupervisor()
    sup.proc = _dummy_proc()
    sent = _spy_signals(monkeypatch, sup.proc)
    monkeypatch.setattr(backend_main.os, "name", "nt")
    try:
        asyncio.run(sup.stop())
    finally:
        if sup.proc.poll() is None:
            sup.proc.kill()
            sup.proc.wait(5)
    assert sup.proc.poll() is not None
    assert signal.SIGINT not in sent  # Windows 不发 SIGINT
    assert signal.SIGTERM in sent     # terminate()（POSIX 宿主上等价 SIGTERM）


def test_supervisor_stop_posix_sends_sigint(monkeypatch):
    sup = backend_main.WorkerSupervisor()
    sup.proc = _dummy_proc()
    sent = _spy_signals(monkeypatch, sup.proc)
    monkeypatch.setattr(backend_main.os, "name", "posix")
    try:
        asyncio.run(sup.stop())
    finally:
        if sup.proc.poll() is None:
            sup.proc.kill()
            sup.proc.wait(5)
    assert sup.proc.poll() is not None
    assert signal.SIGINT in sent  # POSIX 路径不变（worker KeyboardInterrupt 优雅退出）


# ---------------- db：mlx_available 迁移（只增不删）----------------

_OLD_WORKER_STATE = """
CREATE TABLE worker_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pid INTEGER,
    heartbeat REAL,
    model_loaded INTEGER NOT NULL DEFAULT 0,
    model_variant TEXT,
    bits INTEGER,
    sequential INTEGER,
    current_job_id TEXT,
    started_at REAL,
    load_seconds REAL,
    last_error TEXT DEFAULT '',
    mlx_version TEXT DEFAULT '',
    metal_available INTEGER DEFAULT 0,
    device TEXT DEFAULT ''
);
INSERT INTO worker_state (id, pid, model_loaded) VALUES (1, 123, 0);
"""


def test_mlx_available_migration_old_db(tmp_path, monkeypatch):
    """旧库（无 mlx_available 列）→ init_db 补列，默认 0，旧数据保留，幂等。"""
    old = tmp_path / "old.db"
    conn = sqlite3.connect(str(old))
    conn.executescript(_OLD_WORKER_STATE)
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", old)
    monkeypatch.setattr(db._local, "conn", None, raising=False)
    db.init_db()
    ws = db.get_worker_state()
    assert ws["pid"] == 123            # 旧数据保留
    assert ws["mlx_available"] == 0    # 默认保守（启动探针按实际探测写入）
    db.worker_heartbeat(456, mlx_available=1)
    ws = db.get_worker_state()
    assert ws["pid"] == 456 and ws["mlx_available"] == 1
    db.init_db()  # 幂等：列已存在不报错
    assert db.get_worker_state()["mlx_available"] == 1
