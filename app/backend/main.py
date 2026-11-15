"""AuK Studio — FastAPI 入口。

- 只监听 127.0.0.1（默认），不暴露局域网。
- lifespan 内启动并监管推理 worker 子进程（崩溃自动重启，退出时优雅停止）。
- 生产模式托管前端构建产物（app/frontend/dist）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db
from .api_models import router as models_router
from .api_providers import router as providers_router
from .api_system import router as system_router
from .api_voices import router as voices_router
from .routers import router

log = logging.getLogger("auk.backend")

FRONTEND_DIST = config.ROOT / "app" / "frontend" / "dist"


class WorkerSupervisor:
    """拉起并监管单 worker 子进程。"""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.restarts = 0

    def _spawn(self) -> subprocess.Popen:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(config.ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env.setdefault("HF_HUB_OFFLINE", "1")
        env.setdefault("TRANSFORMERS_OFFLINE", "1")
        log.info("启动 worker: %s -m app.backend.worker", config.VENV_PYTHON)
        return subprocess.Popen(
            [str(config.VENV_PYTHON), "-m", "app.backend.worker"],
            cwd=str(config.ROOT), env=env,
            stdout=open(config.LOGS_DIR / "worker.stdout.log", "ab"),
            stderr=subprocess.STDOUT,
        )

    async def run(self) -> None:
        self.proc = self._spawn()
        backoff = 1
        while not self._stop.is_set():
            await asyncio.sleep(2)
            if self.proc and self.proc.poll() is not None:
                code = self.proc.returncode
                if self._stop.is_set():
                    break
                self.restarts += 1
                log.warning("worker 退出 code=%s，%ss 后重启（第 %d 次）", code, backoff, self.restarts)
                db.worker_heartbeat(0, last_error=f"worker 退出 code={code}，正在重启")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                if not self._stop.is_set():
                    self.proc = self._spawn()
            else:
                backoff = 1

    async def start(self) -> None:
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            log.info("停止 worker (SIGINT)")
            self.proc.send_signal(signal.SIGINT)
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.proc.wait, 10)
            except subprocess.TimeoutExpired:
                log.warning("worker 未在 10s 内退出，SIGTERM")
                self.proc.terminate()
                try:
                    await asyncio.get_event_loop().run_in_executor(None, self.proc.wait, 5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        if self._task:
            self._task.cancel()


supervisor = WorkerSupervisor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init_db()
    n = db.mark_interrupted_jobs()
    if n:
        log.info("启动清理：%d 个遗留运行中任务标记为 failed", n)
    await supervisor.start()
    log.info("AuK Studio 后端就绪 | 数据目录 %s", config.DATA_DIR)
    yield
    await supervisor.stop()
    log.info("后端已停止")


app = FastAPI(title="AuK Studio", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(system_router)
app.include_router(models_router)
app.include_router(voices_router)
app.include_router(providers_router)

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


def main() -> None:
    import uvicorn

    port = config.PORT
    # 端口占用时自动选择可用端口（方案 §6）
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((config.HOST, port)) == 0:
            log.warning("端口 %d 被占用，自动选择新端口", port)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind((config.HOST, 0))
                port = s2.getsockname()[1]
    runtime = {"host": config.HOST, "port": port, "pid": os.getpid(), "started_at": __import__("time").time()}
    (config.DATA_DIR / "runtime.json").write_text(__import__("json").dumps(runtime, indent=2))
    print(f"\n  AuK Studio → http://{config.HOST}:{port}\n  API 文档 → http://{config.HOST}:{port}/docs\n", flush=True)
    uvicorn.run(app, host=config.HOST, port=port, log_level="info")


if __name__ == "__main__":
    main()