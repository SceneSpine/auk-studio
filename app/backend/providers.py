"""在线 TTS provider 管理（docs/API_CONTRACT.md §Provider 扩展 v0.3）。

- CRUD：providers 表；api_key 仅存本机 SQLite。
- 隐私：**任何 API 响应与日志不得出现完整 key**；对外只给 masked（尾 4 位）+ has_key。
- base_url 校验：https 任意主机，或 http://127.0.0.1|localhost（防 SSRF 到内网任意地址）。
- test_provider / speech_request：OpenAI 兼容 POST {base_url}/audio/speech（urllib，标准库）。
  错误消息统一脱敏（redact），可安全写入任务 error 与日志。
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from . import db

KIND = "openai_tts"
TEST_TIMEOUT_S = 20
JOB_TIMEOUT_S = 120


class ProviderError(Exception):
    """在线 TTS 请求失败。消息已脱敏（不含完整 key），可直接写日志/任务 error。"""


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
        if kind != KIND:
            raise ValueError(f"kind 仅支持 {KIND}")
        fields["kind"] = kind
    if not partial or "base_url" in data:
        fields["base_url"] = validate_base_url(data.get("base_url") or "")
    if not partial or "model" in data:
        model = (data.get("model") or "").strip()
        if not model:
            raise ValueError("model 不能为空")
        fields["model"] = model
    if not partial or "voice" in data:
        voice = (data.get("voice") or "").strip()
        if not voice:
            raise ValueError("voice 不能为空")
        fields["voice"] = voice
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


# ---------------- HTTP（OpenAI 兼容 /audio/speech） ----------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不跟随重定向（防止 https → http 内网跳转的 SSRF 绕过）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError(f"服务端返回重定向 HTTP {code}，已拒绝跟随（安全策略）")


_opener = urllib.request.build_opener(_NoRedirect)


def speech_request(base_url: str, api_key: str, model: str, voice: str, text: str,
                   *, timeout: float) -> tuple[bytes, str, int]:
    """POST {base_url}/audio/speech → (body, content_type, status)。

    失败抛 ProviderError（含 HTTP 状态码与服务商消息，已脱敏）。
    """
    url = base_url.rstrip("/") + "/audio/speech"
    payload = {"model": model, "input": text, "voice": voice, "response_format": "wav"}
    headers = {"Content-Type": "application/json", "Accept": "audio/wav, audio/mpeg, */*"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with _opener.open(req, timeout=timeout) as resp:
            body = resp.read()
            return body, resp.headers.get("Content-Type", ""), resp.status
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:  # noqa: BLE001
            pass
        msg = ""
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                msg = str(err.get("message") or "")
            elif isinstance(err, str):
                msg = err
            if not msg and isinstance(data, dict):
                msg = str(data.get("message") or "")
        except (ValueError, AttributeError):
            pass
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


def test_provider(provider_id: str) -> dict | None:
    """连通性/鉴权测试：input='test' 的极短 TTS，超时 20s。

    返回 {ok, latency_ms, error?}；provider 不存在 → None（API 层 404）。
    error 不含完整 key。
    """
    row = get_raw(provider_id)
    if not row:
        return None
    key = row.get("api_key") or ""
    t0 = time.monotonic()

    def _ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        validate_base_url(row["base_url"])
        body, _ctype, _status = speech_request(
            row["base_url"], key, row.get("model") or "", row.get("voice") or "",
            "test", timeout=TEST_TIMEOUT_S)
        if not body:
            return {"ok": False, "latency_ms": _ms(), "error": "服务端返回空响应"}
        return {"ok": True, "latency_ms": _ms()}
    except ProviderError as e:
        return {"ok": False, "latency_ms": _ms(), "error": str(e)[:500]}
    except ValueError as e:
        return {"ok": False, "latency_ms": None, "error": str(e)}