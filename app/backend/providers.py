"""远程 AuK provider 管理（docs/API_CONTRACT.md §Provider kind 扩展：auk_remote / hf_space）。

- kind："auk_remote"（远程 AuK Studio 全能力推理）| "hf_space"（HuggingFace AuK Space，
  Gradio 6 协议）+ 内置 local；model/voice 不使用（存空串）。
- CRUD：providers 表；api_key 可选（Bearer：auk_remote 用于自建反代鉴权，hf_space 为 HF token），
  仅存本机 SQLite。
- 隐私：**任何 API 响应与日志不得出现完整 key**；对外只给 masked（尾 4 位）+ has_key。
- base_url 校验：https 任意主机，或 http://127.0.0.1|localhost（防 SSRF 到内网任意地址）。
- HTTP 客户端（urllib，标准库）：可选 Bearer、不跟随重定向、错误消息统一脱敏（redact），
  可安全写入任务 error 与日志。
- 代理：HF 国内直连不通，hf_space（及可选 auk_remote）请求支持 HF_PROXY / AUK_SOCKS_PROXY
  环境变量（SOCKS5，PySocks）。代理地址仅从环境变量读取，不硬编码任何端口。
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from urllib.parse import urlparse

from . import db

try:  # PySocks（SOCKS 代理支持）；缺失时仅影响代理路径，直连不受影响
    import socks
except ImportError:  # pragma: no cover
    socks = None

KIND = "auk_remote"
KIND_HF_SPACE = "hf_space"
KINDS = (KIND, KIND_HF_SPACE)
TEST_TIMEOUT_S = 20
REMOTE_POLL_S = 1.5      # 远程任务轮询间隔
REMOTE_TIMEOUT_S = 600   # 远程任务总超时
HTTP_TIMEOUT_S = 30      # 普通 JSON 请求（创建/轮询/结果/取消）
TRANSFER_TIMEOUT_S = 120  # 音频上传/下载
CANCEL_TIMEOUT_S = 10    # 尽力远程取消

# ---- HF Space（Gradio 6）----
GRADIO_ENDPOINT = "generate_with_pe"        # named endpoint /run_generate_with_pe → call 路径
GRADIO_INFO_PATH = "/gradio_api/info"
GRADIO_TIMEOUT_S = 600                      # 共享 Space 排队 + 冷启动总超时
GRADIO_SSE_POLL_S = 2.0                     # SSE socket 读超时（用于周期性检查取消/总超时）
PROXY_ENV_VARS = ("HF_PROXY", "AUK_SOCKS_PROXY")


class ProviderError(Exception):
    """远程 AuK 请求失败。消息已脱敏（不含完整 key），可直接写日志/任务 error。"""


class GradioCancelled(Exception):
    """HF Space SSE 等待期间用户请求取消（worker 据此标 cancelled，而非 failed）。"""


# ---------------- key 掩码 / 脱敏 ----------------

def mask_key(key: str | None) -> str:
    """尾 4 位掩码，如 '…abcd'；空 key → ''；过短 key 不泄露任何字符。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "…"
    return "…" + key[-4:]


def redact(text: str, api_key: str | None) -> str:
    """把文本中出现的完整 key 替换为 [REDACTED]（防御性兜底）。"""
    if text and api_key:
        text = text.replace(api_key, "[REDACTED]")
    return text


# ---------------- base_url 校验 ----------------

def validate_base_url(base_url: str) -> str:
    """校验并规范化（去尾部斜杠）。非法 → ValueError。

    https 允许任意主机；http 仅允许 127.0.0.1 / localhost（本机 mock/代理），
    其余内网地址一律拒绝（防 SSRF）。不允许携带凭据/query/fragment。
    """
    u = (base_url or "").strip()
    if not u:
        raise ValueError("base_url 不能为空")
    try:
        parsed = urlparse(u)
        host = (parsed.hostname or "").lower()
        _ = parsed.port  # 触发非法端口的 ValueError
    except ValueError:
        raise ValueError("base_url 格式非法") from None
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url 仅支持 https，或 http://127.0.0.1|localhost")
    if not host:
        raise ValueError("base_url 缺少主机名")
    if parsed.username or parsed.password:
        raise ValueError("base_url 不允许携带凭据（user:pass@）")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url 不允许携带 query/fragment")
    if parsed.scheme == "http" and host not in ("127.0.0.1", "localhost"):
        raise ValueError("http 仅允许 127.0.0.1 或 localhost（防 SSRF 到内网）；其他主机请使用 https")
    return u.rstrip("/")


# ---------------- 代理（HF_PROXY / AUK_SOCKS_PROXY，SOCKS5） ----------------

def parse_proxy_url(url: str) -> dict:
    """解析 SOCKS 代理地址 → 配置 dict。非法 → ValueError（消息不回显凭据）。

    支持 socks5h:// / socks5:// / socks4a:// / socks4://（h/a = 远端 DNS 解析）。
    返回 {type, host, port, rdns, username, password}。
    """
    u = (url or "").strip()
    if not u:
        raise ValueError("代理地址为空")
    try:
        parsed = urlparse(u)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise ValueError("代理地址格式非法（需 socks5h://host:port）") from None
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("socks5h", "socks5", "socks4a", "socks4"):
        raise ValueError("代理仅支持 SOCKS（socks5h/socks5/socks4a/socks4）")
    if not host or not port:
        raise ValueError("代理地址缺少主机名或端口（需 socks5h://host:port）")
    if socks is None:
        raise ValueError("SOCKS 代理需要 PySocks（当前环境未安装）")
    ptype = socks.PROXY_TYPE_SOCKS4 if scheme in ("socks4", "socks4a") else socks.PROXY_TYPE_SOCKS5
    return {
        "type": ptype, "host": host, "port": port,
        "rdns": scheme in ("socks5h", "socks4a"),
        "username": parsed.username, "password": parsed.password,
    }


def resolve_proxy() -> dict | None:
    """从 HF_PROXY / AUK_SOCKS_PROXY（按序）读取代理配置；均未设置 → None（直连）。

    设置了但格式非法 → ValueError（由调用方转为 ProviderError / 测试失败信息）。
    """
    for var in PROXY_ENV_VARS:
        v = (os.environ.get(var) or "").strip()
        if v:
            return parse_proxy_url(v)
    return None


def proxy_desc(cfg: dict | None) -> str:
    """代理的可日志描述（host:port，不含凭据）；直连 → 'direct'。"""
    if not cfg:
        return "direct"
    return f"socks://{cfg['host']}:{cfg['port']}"


class _SocksHTTPConnection(http.client.HTTPConnection):
    """经 SOCKS 代理建立 HTTP 连接（PySocks create_connection）。"""

    def __init__(self, host, port=None, *, proxy_cfg=None, timeout=None, **kw):
        super().__init__(host, port, timeout=timeout, **kw)
        self._proxy_cfg = proxy_cfg

    def connect(self):
        cfg = self._proxy_cfg
        self.sock = socks.create_connection(
            (self.host, self.port), timeout=self.timeout,
            proxy_type=cfg["type"], proxy_addr=cfg["host"], proxy_port=cfg["port"],
            proxy_rdns=cfg["rdns"], proxy_username=cfg.get("username"),
            proxy_password=cfg.get("password"),
        )


class _SocksHTTPSConnection(http.client.HTTPSConnection):
    """经 SOCKS 代理建立 HTTPS 连接（SOCKS 之上再 TLS）。"""

    def __init__(self, host, port=None, *, proxy_cfg=None, timeout=None,
                 context=None, check_hostname=None, **kw):
        super().__init__(host, port, timeout=timeout, context=context,
                         check_hostname=check_hostname, **kw)
        self._proxy_cfg = proxy_cfg

    def connect(self):
        cfg = self._proxy_cfg
        raw = socks.create_connection(
            (self.host, self.port), timeout=self.timeout,
            proxy_type=cfg["type"], proxy_addr=cfg["host"], proxy_port=cfg["port"],
            proxy_rdns=cfg["rdns"], proxy_username=cfg.get("username"),
            proxy_password=cfg.get("password"),
        )
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class _SocksHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, proxy_cfg):
        super().__init__()
        self._proxy_cfg = proxy_cfg

    def http_open(self, req):
        return self.do_open(_SocksHTTPConnection, req, proxy_cfg=self._proxy_cfg)


class _SocksHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, proxy_cfg, context=None):
        super().__init__(context=context)
        self._proxy_cfg = proxy_cfg

    def https_open(self, req):
        return self.do_open(_SocksHTTPSConnection, req, proxy_cfg=self._proxy_cfg,
                            context=self._context, check_hostname=self._check_hostname)


def _proxy_for_url(url: str) -> dict | None:
    """环回地址绕过代理（NO_PROXY 语义，本机调试/mock 不走 SOCKS）；其余按环境变量代理。"""
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        host = ""
    if host in ("127.0.0.1", "localhost", "::1"):
        return None
    return resolve_proxy()


def _get_opener(proxy_cfg: dict | None):
    """按代理配置选择 opener。直连复用既有 _opener（行为与旧版完全一致）。"""
    if proxy_cfg is None:
        return _opener
    # ProxyHandler({}) 禁用环境 http(s)_proxy，避免与 SOCKS 冲突；仍不跟随重定向。
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _SocksHTTPHandler(proxy_cfg), _SocksHTTPSHandler(proxy_cfg), _NoRedirect)


# ---------------- CRUD ----------------

def public(row: dict) -> dict:
    """DB 行 → API Provider（绝不包含 api_key 原文）。"""
    key = row.get("api_key") or ""
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "base_url": row["base_url"],
        "model": row.get("model") or "",
        "voice": row.get("voice") or "",
        "enabled": bool(row.get("enabled")),
        "has_key": bool(key),
        "key_masked": mask_key(key),
        "created_at": row["created_at"],
    }


def get_raw(provider_id: str) -> dict | None:
    """内部使用（worker / test）：含 api_key 原文。绝不直接作为 API 响应。"""
    return db.one(db.connect().execute("SELECT * FROM providers WHERE id=?", (provider_id,)))


def get(provider_id: str) -> dict | None:
    row = get_raw(provider_id)
    return public(row) if row else None


def list_providers() -> list[dict]:
    rows = db.rows(db.connect().execute("SELECT * FROM providers ORDER BY created_at DESC"))
    return [public(r) for r in rows]


def _clean_fields(data: dict, *, partial: bool) -> dict:
    """校验并规范化可写字段。partial=True 时仅处理 data 中出现的键。"""
    fields: dict = {}
    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("name 不能为空")
        fields["name"] = name
    if not partial or "kind" in data:
        kind = data.get("kind") or KIND
        if kind not in KINDS:
            raise ValueError(f"kind 仅支持 {' / '.join(KINDS)}")
        fields["kind"] = kind
    if not partial or "base_url" in data:
        fields["base_url"] = validate_base_url(data.get("base_url") or "")
    # model/voice：auk_remote / hf_space 均不使用，统一存空串（列保留兼容旧库）；提交值被忽略
    if not partial:
        fields["model"] = ""
        fields["voice"] = ""
    if not partial or "enabled" in data:
        fields["enabled"] = int(bool(data.get("enabled", True)))
    # api_key：空串/None = 不修改（PUT 语义）；创建时允许为空（无鉴权服务）
    if data.get("api_key"):
        fields["api_key"] = data["api_key"]
    elif not partial:
        fields["api_key"] = ""
    return fields


def create(data: dict) -> dict:
    fields = _clean_fields(data, partial=False)
    pid = db.new_id("prov")
    with db.tx() as conn:
        conn.execute(
            """INSERT INTO providers (id, name, kind, base_url, api_key, model, voice, enabled, created_at)
               VALUES (:id, :name, :kind, :base_url, :api_key, :model, :voice, :enabled, :created_at)""",
            {**fields, "id": pid, "created_at": time.time()},
        )
    return get(pid)


def update(provider_id: str, data: dict) -> dict | None:
    if not get_raw(provider_id):
        return None
    fields = _clean_fields(data, partial=True)
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        with db.tx() as conn:
            conn.execute(f"UPDATE providers SET {sets} WHERE id=?", (*fields.values(), provider_id))
    return get(provider_id)


def delete(provider_id: str) -> bool:
    with db.tx() as conn:
        cur = conn.execute("DELETE FROM providers WHERE id=?", (provider_id,))
        return cur.rowcount > 0


# ---------------- HTTP（远程 AuK Studio /api/*） ----------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不跟随重定向（防止 https → http 内网跳转的 SSRF 绕过）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError(f"服务端返回重定向 HTTP {code}，已拒绝跟随（安全策略）")


_opener = urllib.request.build_opener(_NoRedirect)


def _error_message(raw: bytes) -> str:
    """从响应体提取服务端错误消息（AuK 风格 {detail} 优先，兼容 {error}/{message}）。"""
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    for k in ("detail", "error"):
        v = data.get(k)
        if isinstance(v, dict):
            m = str(v.get("message") or "")
            if m:
                return m
        elif isinstance(v, str) and v.strip():
            return v
    return str(data.get("message") or "")


def remote_request(base_url: str, api_key: str, method: str, path: str, *,
                   payload: dict | None = None, data: bytes | None = None,
                   content_type: str | None = None, timeout: float) -> tuple[bytes, str, int]:
    """向远程 AuK Studio 发请求 → (body, content_type, status)。

    payload=dict → JSON 请求体；data=bytes → 原始请求体（multipart 等，配 content_type）。
    可选 Bearer；不跟随重定向。失败抛 ProviderError（含 HTTP 状态码与服务端消息，已脱敏）。
    """
    url = base_url.rstrip("/") + path
    headers = {"Accept": "application/json, audio/wav, audio/mpeg, */*"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif data is not None:
        body = data
        headers["Content-Type"] = content_type or "application/octet-stream"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        proxy_cfg = _proxy_for_url(url)
    except ValueError as e:
        raise ProviderError(str(e)) from None
    opener = _get_opener(proxy_cfg)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get("Content-Type", ""), resp.status
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:  # noqa: BLE001
            pass
        msg = _error_message(raw)
        if not msg:
            msg = raw.decode("utf-8", "replace").strip()[:300] or str(e.reason or "")
        raise ProviderError(redact(f"HTTP {e.code}: {msg[:500]}", api_key)) from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise ProviderError(f"请求超时（{timeout:g}s）") from None
        raise ProviderError(redact(f"连接失败: {e.reason}", api_key)) from None
    except (TimeoutError, socket.timeout):
        raise ProviderError(f"请求超时（{timeout:g}s）") from None
    except OSError as e:
        raise ProviderError(redact(f"网络错误: {e}", api_key)) from None


def remote_json(base_url: str, api_key: str, method: str, path: str, *,
                payload: dict | None = None, timeout: float = HTTP_TIMEOUT_S, **kw) -> dict:
    """remote_request 的 JSON 封装：响应必须是 JSON 对象，否则 ProviderError。"""
    body, _ctype, _status = remote_request(base_url, api_key, method, path,
                                         payload=payload, timeout=timeout, **kw)
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ProviderError("远程响应不是合法 JSON") from None
    if not isinstance(data, dict):
        raise ProviderError("远程响应格式异常（应为 JSON 对象）")
    return data


def remote_upload_audio(base_url: str, api_key: str, wav_bytes: bytes, *,
                        filename: str = "input.wav", timeout: float = TRANSFER_TIMEOUT_S) -> str:
    """multipart POST {base}/api/audio/upload → 远程 audio_id。"""
    boundary = uuid.uuid4().hex
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: audio/wav\r\n\r\n").encode("utf-8")
    mp = head + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    data = remote_json(base_url, api_key, "POST", "/api/audio/upload", data=mp,
                       content_type=f"multipart/form-data; boundary={boundary}", timeout=timeout)
    aid = data.get("id")
    if not aid or not isinstance(aid, str):
        raise ProviderError("远程上传未返回 audio_id")
    return aid


def remote_download(base_url: str, api_key: str, path: str, *,
                    timeout: float = TRANSFER_TIMEOUT_S) -> tuple[bytes, str]:
    """GET 下载字节 → (body, content_type)。"""
    body, ctype, _status = remote_request(base_url, api_key, "GET", path, timeout=timeout)
    return body, ctype


# ---------------- HF Space（Gradio 6）客户端 ----------------

def gradio_info(base_url: str, api_key: str, *, timeout: float = TEST_TIMEOUT_S) -> dict:
    """GET {base}/gradio_api/info → JSON（含 named_endpoints）。"""
    return remote_json(base_url, api_key, "GET", GRADIO_INFO_PATH, timeout=timeout)


def gradio_upload(base_url: str, api_key: str, wav_bytes: bytes, *,
                  filename: str = "input.wav", timeout: float = TRANSFER_TIMEOUT_S) -> str:
    """multipart POST {base}/gradio_api/upload（字段名 files）→ 远端文件 path。"""
    boundary = uuid.uuid4().hex
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            "Content-Type: audio/wav\r\n\r\n").encode("utf-8")
    mp = head + wav_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    body, _ctype, _status = remote_request(
        base_url, api_key, "POST", "/gradio_api/upload", data=mp,
        content_type=f"multipart/form-data; boundary={boundary}", timeout=timeout)
    try:
        paths = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ProviderError("HF Space 上传响应不是合法 JSON") from None
    if not isinstance(paths, list) or not paths or not isinstance(paths[0], str):
        raise ProviderError("HF Space 上传未返回文件路径")
    return paths[0]


def gradio_call(base_url: str, api_key: str, data_array: list, *,
                timeout: float = HTTP_TIMEOUT_S) -> str:
    """POST {base}/gradio_api/call/generate_with_pe {"data":[8参]} → event_id。"""
    resp = remote_json(base_url, api_key, "POST", f"/gradio_api/call/{GRADIO_ENDPOINT}",
                       payload={"data": data_array}, timeout=timeout)
    eid = resp.get("event_id")
    if not eid or not isinstance(eid, str):
        raise ProviderError("HF Space 未返回 event_id")
    return eid


def gradio_open_sse(base_url: str, api_key: str, event_id: str, *, timeout: float):
    """打开 GET {base}/gradio_api/call/generate_with_pe/{event_id} 的 SSE 流（返回响应对象）。

    timeout 为 socket 读超时（供周期性检查取消/总超时）；不跟随重定向；失败抛 ProviderError。
    """
    url = base_url.rstrip("/") + f"/gradio_api/call/{GRADIO_ENDPOINT}/{event_id}"
    headers = {"Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        proxy_cfg = _proxy_for_url(url)
    except ValueError as e:
        raise ProviderError(str(e)) from None
    opener = _get_opener(proxy_cfg)
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:  # noqa: BLE001
            pass
        msg = _error_message(raw) or raw.decode("utf-8", "replace").strip()[:300] or str(e.reason or "")
        raise ProviderError(redact(f"HTTP {e.code}: {msg[:500]}", api_key)) from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise ProviderError(f"SSE 连接超时（{timeout:g}s）") from None
        raise ProviderError(redact(f"SSE 连接失败: {e.reason}", api_key)) from None
    except (TimeoutError, socket.timeout):
        raise ProviderError(f"SSE 连接超时（{timeout:g}s）") from None
    except OSError as e:
        raise ProviderError(redact(f"SSE 网络错误: {e}", api_key)) from None


def _extract_filedata(data_str: str, api_key: str) -> dict:
    """从 process_completed 的 data 提取 output.data[0]（FileData）。"""
    try:
        obj = json.loads(data_str)
    except (ValueError, TypeError):
        raise ProviderError("HF Space process_completed 数据不是合法 JSON") from None
    output = obj.get("output") if isinstance(obj, dict) else None
    data = output.get("data") if isinstance(output, dict) else None
    if not isinstance(data, list) or not data:
        raise ProviderError("HF Space 结果缺少 output.data")
    fd = data[0]
    if not isinstance(fd, dict) or not (fd.get("path") or fd.get("url")):
        raise ProviderError("HF Space 结果 FileData 缺少 path/url")
    return fd


def gradio_sse_wait(base_url: str, api_key: str, event_id: str, *,
                    total_timeout: float = GRADIO_TIMEOUT_S, cancelled=None,
                    poll_s: float = GRADIO_SSE_POLL_S, on_event=None) -> dict:
    """读取 SSE 直到 process_completed，返回 FileData。

    - cancelled()：返回 True → 抛 GradioCancelled（中断 SSE）。
    - 总超时 total_timeout → ProviderError；event:error / 流提前结束 → ProviderError。
    - socket 读超时 poll_s 仅用于周期性醒来检查取消/总超时（不视为失败）。
    """
    deadline = time.monotonic() + total_timeout
    resp = gradio_open_sse(base_url, api_key, event_id, timeout=poll_s)
    try:
        event_name = ""
        data_lines: list[str] = []
        while True:
            if cancelled is not None and cancelled():
                raise GradioCancelled("用户取消")
            if time.monotonic() > deadline:
                raise ProviderError(f"HF Space 任务超时（{total_timeout:g}s，event {event_id}）")
            try:
                raw = resp.readline()
            except (TimeoutError, socket.timeout):
                continue  # 暂无数据：回到循环检查取消/总超时
            except OSError as e:
                raise ProviderError(redact(f"SSE 连接中断: {e}", api_key)) from None
            if not raw:
                raise ProviderError("HF Space SSE 流提前结束（未收到 process_completed）")
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line == "":
                if event_name:
                    data_str = "\n".join(data_lines)
                    if on_event is not None:
                        on_event(event_name, data_str)
                    if event_name == "process_completed":
                        return _extract_filedata(data_str, api_key)
                    if event_name == "error":
                        raise ProviderError(redact(f"HF Space 返回错误: {data_str[:300]}", api_key))
                event_name = ""
                data_lines = []
                continue
            if line.startswith(":"):
                continue  # SSE 注释 / heartbeat
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
            # 其余字段（id:/retry:）忽略
    finally:
        resp.close()


def gradio_download(base_url: str, api_key: str, filedata: dict, *,
                    timeout: float = TRANSFER_TIMEOUT_S) -> tuple[bytes, str]:
    """下载 FileData 音频 → (body, content_type)。

    优先同源 url（绝不离开 Space 源，防 SSRF）；否则回退 {base}/gradio_api/file={path}。
    """
    path = filedata.get("path") or ""
    url = filedata.get("url") or ""
    dl = None
    if url:
        pu, pb = urlparse(url), urlparse(base_url)
        if pu.scheme in ("http", "https") and pu.netloc == pb.netloc:
            dl = pu.path + (("?" + pu.query) if pu.query else "")
    if dl is None:
        if not path:
            raise ProviderError("HF Space FileData 缺少可下载路径")
        dl = "/gradio_api/file=" + path
    body, ctype, _status = remote_request(base_url, api_key, "GET", dl, timeout=timeout)
    return body, ctype


def test_provider(provider_id: str) -> dict | None:
    """连通性测试（可选 Bearer），超时 20s。

    - auk_remote：GET {base}/api/health，status=ok 即通过。
    - hf_space：GET {base}/gradio_api/info，named_endpoints 含 /run_generate_with_pe 即通过。
    返回 {ok, latency_ms, error?}；provider 不存在 → None（API 层 404）。error 不含完整 key。
    """
    row = get_raw(provider_id)
    if not row:
        return None
    key = row.get("api_key") or ""
    t0 = time.monotonic()

    def _ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        base = validate_base_url(row["base_url"])
        if row.get("kind") == KIND_HF_SPACE:
            data = gradio_info(base, key, timeout=TEST_TIMEOUT_S)
            endpoints = data.get("named_endpoints") or {}
            if f"/run_{GRADIO_ENDPOINT}" not in endpoints:
                return {"ok": False, "latency_ms": _ms(),
                        "error": f"Space 未暴露 /run_{GRADIO_ENDPOINT}（非 AuK Space 或协议不符）"}
            return {"ok": True, "latency_ms": _ms()}
        data = remote_json(base, key, "GET", "/api/health", timeout=TEST_TIMEOUT_S)
        if data.get("status") != "ok":
            return {"ok": False, "latency_ms": _ms(),
                    "error": f"远程健康检查未通过: {str(data.get('status') or '未知')[:200]}"}
        return {"ok": True, "latency_ms": _ms()}
    except ProviderError as e:
        return {"ok": False, "latency_ms": _ms(), "error": str(e)[:500]}
    except ValueError as e:
        return {"ok": False, "latency_ms": None, "error": str(e)}