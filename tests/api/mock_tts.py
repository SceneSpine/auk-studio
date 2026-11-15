"""线程版 mock OpenAI 兼容 TTS 服务器（仅测试用，绑定 127.0.0.1，标准库实现）。

- POST {base}/audio/speech：校验 Bearer key（可选）、返回**真实 WAV 字节**（正弦合成）。
- 可配置：required_key / fail_status / fail_message / content_type / delay_s / wav_seconds /
  on_request 回调；server.requests 记录收到的请求（path/headers/body）供断言。
- 错误响应为 OpenAI 风格 {"error": {"message, type, code}}，**不回显完整 key**。

用法（测试）：
    from mock_tts import mock_tts
    with mock_tts(required_key="sk-…abcd") as srv:
        ...  # srv.base_url == "http://127.0.0.1:<随机端口>/v1"

用法（live 验证）：
    .venv-auk/bin/python tests/api/mock_tts.py 7899 --key ***
"""
from __future__ import annotations

import io
import json
import math
import struct
import threading
import time
import wave
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 测试静默；CLI verbose 时输出到 stderr
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, obj: dict) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json")

    def _error(self, status: int, message: str, code: str = "mock_error") -> None:
        self._send_json(status, {"error": {"message": message, "type": "invalid_request_error", "code": code}})

    def do_GET(self):  # noqa: N802
        self._error(405, "仅支持 POST /audio/speech")

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not path.endswith("/audio/speech"):
            self._error(404, f"未知路径 {path}")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body 必须是对象")
        except (ValueError, json.JSONDecodeError):
            self._error(400, "请求体不是合法 JSON")
            return
        headers = {k.lower(): v for k, v in self.headers.items()}
        self.server.requests.append({"path": path, "headers": headers, "body": body})
        if self.server.on_request is not None:
            self.server.on_request(body)
        if self.server.fail_status:
            self._error(self.server.fail_status, self.server.fail_message or "mock 注入错误", "mock_injected")
            return
        key = self.server.required_key
        if key and headers.get("authorization") != f"Bearer {key}":
            # 与真实服务商一致：不回显完整 key
            self._error(401, "Incorrect API key provided.", "invalid_api_key")
            return
        if not isinstance(body.get("input"), str) or not body["input"].strip():
            self._error(400, "input 不能为空", "missing_input")
            return
        if self.server.delay_s > 0:
            time.sleep(self.server.delay_s)
        ctype = self.server.content_type or "audio/wav"
        self._send(200, make_wav_bytes(self.server.wav_seconds), ctype)


class MockTTSServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr=("127.0.0.1", 0), *, required_key: str | None = None,
                 fail_status: int | None = None, fail_message: str = "",
                 content_type: str = "audio/wav", delay_s: float = 0.0,
                 wav_seconds: float = 0.5, on_request=None, verbose: bool = False):
        super().__init__(addr, _Handler)
        self.required_key = required_key
        self.fail_status = fail_status
        self.fail_message = fail_message
        self.content_type = content_type
        self.delay_s = delay_s
        self.wav_seconds = wav_seconds
        self.on_request = on_request
        self.verbose = verbose
        self.requests: list[dict] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1"


@contextmanager
def mock_tts(**kwargs):
    """启动线程版 mock，yield MockTTSServer；退出时关闭。kwargs 见 MockTTSServer。"""
    httpd = MockTTSServer(**kwargs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Mock OpenAI 兼容 TTS 服务器（仅测试）")
    ap.add_argument("port", nargs="?", type=int, default=7899)
    ap.add_argument("--key", default=None, help="设置后要求 Authorization: Bearer <key>")
    ap.add_argument("--seconds", type=float, default=1.0, help="返回 WAV 时长")
    args = ap.parse_args()
    httpd = MockTTSServer(("127.0.0.1", args.port), required_key=args.key,
                          wav_seconds=args.seconds, verbose=True)
    print(f"Mock TTS → {httpd.base_url}/audio/speech（鉴权：{'开' if args.key else '关'}）", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()