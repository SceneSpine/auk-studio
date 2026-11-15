"""线程版 mock HuggingFace AuK Space（Gradio 6 协议，仅测试用，绑定 127.0.0.1，标准库）。

实现契约 §hf_space 的 Space 端点：
- GET  /gradio_api/info（named_endpoints 含 /run_generate_with_pe）
- POST /gradio_api/upload（multipart files，记录字节，返回 [path]）
- POST /gradio_api/call/generate_with_pe {"data":[8参]} → {event_id}
- GET  /gradio_api/call/generate_with_pe/{event_id}（SSE：process_starts → generating/heartbeat
       → process_completed，output.data[0]=FileData）
- GET  /gradio_api/file={path}（返回**真实 WAV 字节**，正弦合成）

可配置：required_key / fail_info / fail_upload / fail_call / fail_message / sse_error /
hang / heartbeats_before_done / heartbeat_interval / wav_seconds / content_type /
omit_url / omit_endpoint / redirect_to / on_request 回调；
server.requests 记录收到的请求（method/path/headers/body）；server.calls 记录每次 call 的
data 数组（供参数映射断言）；server.uploads / server.files 记录字节。
错误响应为 {"detail": ...}，**不回显完整 key**。

用法（测试）：
    from mock_gradio import mock_gradio
    with mock_gradio(required_key="hf_…abcd") as srv:
        ...  # srv.base_url == "http://127.0.0.1:<随机端口>"
"""
from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mock_auk import _parse_multipart, make_wav_bytes

ENDPOINT = "generate_with_pe"
CALL_PATH = f"/gradio_api/call/{ENDPOINT}"
FILE_PREFIX = "/gradio_api/file="


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 测试静默
        pass

    # ---- 基础响应 ----
    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._send_json(status, {"detail": message})

    def _authed(self, headers: dict) -> bool:
        key = self.server.required_key
        return not key or headers.get("authorization") == f"Bearer {key}"

    def _headers(self) -> dict:
        return {k.lower(): v for k, v in self.headers.items()}

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            return body if isinstance(body, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def _record(self, method: str, path: str, body=None, **extra) -> dict:
        rec = {"method": method, "path": path, "headers": self._headers(), "body": body, **extra}
        self.server.requests.append(rec)
        if self.server.on_request is not None:
            self.server.on_request(method, path, body)
        return rec

    # ---- GET ----
    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        srv = self.server
        headers = self._headers()

        if path == "/gradio_api/info":
            self._record("GET", path)
            if not self._authed(headers):
                self._error(401, "鉴权失败")
                return
            if srv.redirect_to:
                self._send(302, b"", "text/plain", {"Location": srv.redirect_to})
                return
            if srv.fail_info:
                self._error(srv.fail_info, "mock info 注入错误")
                return
            named = {} if srv.omit_endpoint else {
                f"/run_{ENDPOINT}": {
                    "parameters": [
                        {"parameter_name": "use_pe", "type": "bool"},
                        {"parameter_name": "variant", "type": "str"},
                        {"parameter_name": "audio", "type": "FileData|null"},
                        {"parameter_name": "instruction", "type": "str"},
                        {"parameter_name": "gen_seconds", "type": "float"},
                        {"parameter_name": "nfe", "type": "float"},
                        {"parameter_name": "cfg", "type": "float"},
                        {"parameter_name": "seed", "type": "float"},
                    ],
                    "returns": [{"parameter_name": "audio", "type": "FileData"}],
                },
            }
            self._send_json(200, {"named_endpoints": named, "unnamed_endpoints": {}})
            return

        m = re.fullmatch(re.escape(CALL_PATH) + r"/([^/]+)", path)
        if m:
            self._record("GET", path)
            if not self._authed(headers):
                self._error(401, "鉴权失败")
                return
            self._sse(m.group(1))
            return

        if path.startswith(FILE_PREFIX):
            self._record("GET", path)
            if not self._authed(headers):
                self._error(401, "鉴权失败")
                return
            fpath = path[len(FILE_PREFIX):]
            data = srv.files.get(fpath)
            if data is None:
                self._error(404, "文件不存在")
                return
            self._send(200, data, srv.content_type or "audio/wav")
            return

        self._record("GET", path)
        self._error(404, f"未知路径 {path}")

    # ---- POST ----
    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        headers = self._headers()
        srv = self.server

        if path == "/gradio_api/upload":
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
            up_path = f"/tmp/gradio/up{len(srv.uploads) + 1}/{filename}"
            srv.uploads[up_path] = data
            self._send_json(200, [up_path])
            return

        if path == CALL_PATH:
            body = self._read_json()
            self._record("POST", path, body)
            if not self._authed(headers):
                self._error(401, "鉴权失败")
                return
            if srv.fail_call:
                self._error(srv.fail_call, srv.fail_message or "mock call 注入错误")
                return
            if body is None or not isinstance(body.get("data"), list):
                self._error(400, "请求体需为 {data:[...]}")
                return
            eid = f"evt_mock{len(srv.calls) + 1}"
            srv.calls[eid] = {"data": body["data"]}
            self._send_json(200, {"event_id": eid})
            return

        self._record("POST", path, None)
        self._error(404, f"未知路径 {path}")

    # ---- SSE ----
    def _sse(self, event_id: str) -> None:
        srv = self.server
        if event_id not in srv.calls:
            self._error(404, "event 不存在")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(name: str, data) -> None:
            payload = f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            self.wfile.write(payload.encode("utf-8"))
            self.wfile.flush()

        try:
            emit("process_starts", None)
            if srv.hang:
                while True:  # 永不完成：客户端总超时/取消后断开 → OSError 退出
                    emit("heartbeat", None)
                    time.sleep(srv.heartbeat_interval)
            for _ in range(srv.heartbeats_before_done):
                emit("process_generating", None)
                time.sleep(srv.heartbeat_interval)
            if srv.sse_error:
                emit("error", {"error": srv.fail_message or "mock SSE 注入错误"})
                return
            fpath = f"/tmp/gradio/out{len(srv.files) + 1}/audio.wav"
            srv.files[fpath] = make_wav_bytes(srv.wav_seconds)
            fd = {"path": fpath, "meta": {"_type": "gradio.FileData"}}
            if not srv.omit_url:
                fd["url"] = f"{srv.base_url}{FILE_PREFIX}{fpath}"
            emit("process_completed", {"output": {"data": [fd]}, "duration": srv.wav_seconds})
        except (BrokenPipeError, ConnectionResetError, OSError):
            return  # 客户端断开（取消/超时）


class MockGradioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr=("127.0.0.1", 0), *, required_key: str | None = None,
                 fail_info: int | None = None, fail_upload: int | None = None,
                 fail_call: int | None = None, fail_message: str = "",
                 sse_error: bool = False, hang: bool = False,
                 heartbeats_before_done: int = 1, heartbeat_interval: float = 0.02,
                 wav_seconds: float = 0.5, content_type: str = "audio/wav",
                 omit_url: bool = False, omit_endpoint: bool = False,
                 redirect_to: str = "", on_request=None):
        super().__init__(addr, _Handler)
        self.required_key = required_key
        self.fail_info = fail_info
        self.fail_upload = fail_upload
        self.fail_call = fail_call
        self.fail_message = fail_message
        self.sse_error = sse_error
        self.hang = hang
        self.heartbeats_before_done = heartbeats_before_done
        self.heartbeat_interval = heartbeat_interval
        self.wav_seconds = wav_seconds
        self.content_type = content_type
        self.omit_url = omit_url
        self.omit_endpoint = omit_endpoint
        self.redirect_to = redirect_to
        self.on_request = on_request
        self.requests: list[dict] = []
        self.uploads: dict[str, bytes] = {}
        self.calls: dict[str, dict] = {}
        self.files: dict[str, bytes] = {}

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


@contextmanager
def mock_gradio(**kwargs):
    """启动线程版 mock Space，yield MockGradioServer；退出时关闭。kwargs 见 MockGradioServer。"""
    httpd = MockGradioServer(**kwargs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)