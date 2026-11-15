"""线程版 mock 远程 AuK Studio 服务器（仅测试用，绑定 127.0.0.1，标准库实现）。

实现契约 §auk_remote 的远程端点：
- GET  /api/health
- POST /api/audio/upload（multipart，记录字节，返回 audio_id）
- POST /api/jobs · GET /api/jobs/{id} · POST /api/jobs/{id}/cancel
- GET  /api/jobs/{id}/result · GET /api/files/{id}（返回**真实 WAV 字节**，正弦合成）

可配置：required_key / fail_health / fail_create / fail_upload / fail_job_error /
hang / polls_before_done / wav_seconds / content_type / redirect_to / on_request 回调；
server.requests 记录收到的请求（method/path/headers/body）供断言。
错误响应为 AuK 风格 {"detail": ...}，**不回显完整 key**。

用法（测试）：
    from mock_auk import mock_auk
    with mock_auk(required_key="sk-…abcd") as srv:
        ...  # srv.base_url == "http://127.0.0.1:<随机端口>"
"""
from __future__ import annotations

import io
import json
import math
import re
import struct
import threading
import time
import wave
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODES = ("replace", "full", "custom", "tts", "instruct_tts", "timbre", "emotion")


def make_wav_bytes(seconds: float = 0.5, sr: int = 24000, freq: float = 440.0) -> bytes:
    """合成正弦 WAV（16-bit mono）——真实可解码的音频字节。"""
    buf = io.BytesIO()
    n = int(seconds * sr)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            v = int(12000 * math.sin(2 * math.pi * freq * i / sr))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def _parse_multipart(body: bytes, content_type: str) -> tuple[str, bytes]:
    """极简 multipart 解析 → (filename, file_bytes)。仅用于测试 mock。"""
    m = re.search(r"boundary=([^;]+)", content_type or "")
    if not m:
        raise ValueError("缺少 boundary")
    boundary = m.group(1).strip().encode("utf-8")
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition" not in part:
            continue
        header_blob, _, content = part.partition(b"\r\n\r\n")
        fm = re.search(r'filename="([^"]*)"', header_blob.decode("utf-8", "replace"))
        if fm:
            if content.endswith(b"\r\n"):
                content = content[:-2]
            return fm.group(1), content
    raise ValueError("multipart 中无文件部分")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 测试静默
        pass

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, obj: dict) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._send_json(status, {"detail": message})

    def _authed(self, headers: dict) -> bool:
        key = self.server.required_key
        return not key or headers.get("authorization") == f"Bearer {key}"

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            return body if isinstance(body, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def _record(self, method: str, path: str, body=None, **extra) -> dict:
        headers = {k.lower(): v for k, v in self.headers.items()}
        rec = {"method": method, "path": path, "headers": headers, "body": body, **extra}
        self.server.requests.append(rec)
        if self.server.on_request is not None:
            self.server.on_request(method, path, body)
        return rec

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        self._record("GET", path)
        if not self._authed({k.lower(): v for k, v in self.headers.items()}):
            self._error(401, "鉴权失败")
            return
        srv = self.server
        if path == "/api/health":
            if srv.redirect_to:
                self._send(302, b"", "text/plain", {"Location": srv.redirect_to})
                return
            if srv.fail_health:
                self._error(srv.fail_health, "mock 健康检查注入错误")
                return
            self._send_json(200, {"status": "ok", "app": "AuK Studio (mock)", "time": time.time()})
            return
        m = re.fullmatch(r"/api/jobs/([^/]+)", path)
        if m:
            job = srv.jobs.get(m.group(1))
            if not job:
                self._error(404, "任务不存在")
                return
            self._send_json(200, self._advance(job))
            return
        m = re.fullmatch(r"/api/jobs/([^/]+)/result", path)
        if m:
            job = srv.jobs.get(m.group(1))
            if not job:
                self._error(404, "任务不存在")
                return
            self._send_json(200, {"job": job, "files": job.get("files", []), "audio": None})
            return
        m = re.fullmatch(r"/api/files/([^/]+)", path)
        if m:
            data = srv.files.get(m.group(1))
            if data is None:
                self._error(404, "文件不存在")
                return
            self._send(200, data, srv.content_type or "audio/wav")
            return
        self._error(404, f"未知路径 {path}")

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        headers = {k.lower(): v for k, v in self.headers.items()}
        srv = self.server
        if path == "/api/audio/upload":
            length = int(headers.get("content-length") or 0)
            raw = self.rfile.read(length)
            try:
                filename, data = _parse_multipart(raw, headers.get("content-type", ""))
            except ValueError as e:
                self._record("POST", path, None)
                self._error(400, f"multipart 解析失败: {e}")
                return
            self._record("POST", path, None, upload_name=filename, upload_bytes=len(data))
            if not self._authed(headers):
                self._error(401, "鉴权失败")
                return
            if srv.fail_upload:
                self._error(srv.fail_upload, "mock 上传注入错误")
                return
            aid = f"aud_mock{len(srv.uploads) + 1}"
            srv.uploads[aid] = data
            self._send_json(200, {"id": aid, "original_name": filename, "duration": 1.0,
                                  "sample_rate": 24000, "channels": 1})
            return
        body = self._read_json()
        self._record("POST", path, body)
        if not self._authed(headers):
            self._error(401, "鉴权失败")
            return
        if path == "/api/jobs":
            if srv.fail_create:
                self._error(srv.fail_create, srv.fail_message or "mock 创建注入错误")
                return
            if body is None:
                self._error(400, "请求体不是合法 JSON")
                return
            mode = body.get("mode")
            if mode not in MODES:
                self._error(400, f"未知 mode: {mode}")
                return
            if mode != "instruct_tts" and body.get("audio_id") not in srv.uploads:
                self._error(404, "音频不存在")
                return
            jid = f"job_mock{len(srv.jobs) + 1}"
            srv.jobs[jid] = {"id": jid, "status": "queued", "stage_detail": "排队",
                             "error": "", "payload": body, "polls": 0, "files": []}
            self._send_json(200, srv.jobs[jid])
            return
        m = re.fullmatch(r"/api/jobs/([^/]+)/cancel", path)
        if m:
            job = srv.jobs.get(m.group(1))
            if not job:
                self._error(404, "任务不存在")
                return
            if job["status"] in ("completed", "failed", "cancelled"):
                self._error(409, f"任务已处于终态 {job['status']}")
                return
            job["status"] = "cancelled"
            job["cancel_requested"] = 1
            self._send_json(200, {"ok": True, "state": "stop_requested"})
            return
        self._error(404, f"未知路径 {path}")

    def _advance(self, job: dict) -> dict:
        """每次 GET 推进一步：queued/processing → completed（或注入 failed/hang）。"""
        srv = self.server
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        job["polls"] += 1
        if srv.hang:
            job["status"] = "processing"
            job["stage_detail"] = "推理中（mock hang）"
            return job
        if srv.fail_job_error and job["polls"] >= 1:
            job["status"] = "failed"
            job["error"] = srv.fail_job_error
            return job
        if job["polls"] >= srv.polls_before_done:
            job["status"] = "completed"
            job["stage_detail"] = "完成"
            fid = f"file_mock{len(srv.files) + 1}"
            srv.files[fid] = make_wav_bytes(srv.wav_seconds)
            job["files"] = [{"id": fid, "kind": "candidate", "label": "生成候选（整段）",
                             "url": f"/api/files/{fid}"}]
        else:
            job["status"] = "processing"
            job["stage_detail"] = "推理中"
        return job


class MockAuKServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr=("127.0.0.1", 0), *, required_key: str | None = None,
                 fail_health: int | None = None, fail_create: int | None = None,
                 fail_upload: int | None = None, fail_message: str = "",
                 fail_job_error: str = "", hang: bool = False,
                 polls_before_done: int = 2, wav_seconds: float = 0.5,
                 content_type: str = "audio/wav", redirect_to: str = "",
                 on_request=None):
        super().__init__(addr, _Handler)
        self.required_key = required_key
        self.fail_health = fail_health
        self.fail_create = fail_create
        self.fail_upload = fail_upload
        self.fail_message = fail_message
        self.fail_job_error = fail_job_error
        self.hang = hang
        self.polls_before_done = polls_before_done
        self.wav_seconds = wav_seconds
        self.content_type = content_type
        self.redirect_to = redirect_to
        self.on_request = on_request
        self.requests: list[dict] = []
        self.uploads: dict[str, bytes] = {}
        self.jobs: dict[str, dict] = {}
        self.files: dict[str, bytes] = {}

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


@contextmanager
def mock_auk(**kwargs):
    """启动线程版 mock，yield MockAuKServer；退出时关闭。kwargs 见 MockAuKServer。"""
    httpd = MockAuKServer(**kwargs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)