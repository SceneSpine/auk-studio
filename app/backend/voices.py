"""本地参考音色库（docs/API_CONTRACT.md §voices）。

- consent_confirmed 必须 true（否则 403）；固定确认文案，confirmed_at=now。
- 删除音色只删记录，**不删除音频文件**（可能被任务引用）。
- 音色解析为音频路径供 tts 任务使用；归档音色不可用于新任务。
"""
from __future__ import annotations

import json
import time

from . import db

CONSENT_STATEMENT = "我确认对该参考声音拥有合法使用权，仅在本机用于非商业研究/评估用途"
DEFAULT_ALLOWED_USE = "non-commercial research/evaluation on this device"


def _hydrate(row: dict) -> dict:
    v = dict(row)
    try:
        v["tags"] = json.loads(v.pop("tags_json", "") or "[]")
    except ValueError:
        v["tags"] = []
    try:
        consent = json.loads(v.pop("consent_json", "") or "{}")
    except ValueError:
        consent = {}
    v["consent"] = {
        "confirmed": bool(consent.get("confirmed")),
        "statement": consent.get("statement", ""),
        "confirmed_at": consent.get("confirmed_at"),
    }
    v["archived"] = bool(v.get("archived"))
    v["audio"] = db.get_audio(v["audio_id"])
    return v


def create(data: dict) -> dict:
    vid = db.new_id("voice")
    consent = {"confirmed": True, "statement": CONSENT_STATEMENT, "confirmed_at": time.time()}
    with db.tx() as conn:
        conn.execute(
            """INSERT INTO voices (id, name, description, tags_json, audio_id, source, consent_json,
               allowed_use, job_id, created_at, archived)
               VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
            (vid, data["name"], data.get("description", ""), json.dumps(data.get("tags", []), ensure_ascii=False),
             data["audio_id"], data.get("source", "upload"), json.dumps(consent, ensure_ascii=False),
             data.get("allowed_use") or DEFAULT_ALLOWED_USE, data.get("job_id"), time.time()),
        )
    return get(vid)


def get(voice_id: str) -> dict | None:
    row = db.one(db.connect().execute("SELECT * FROM voices WHERE id=?", (voice_id,)))
    return _hydrate(row) if row else None


def list_voices(include_archived: bool = False) -> list[dict]:
    if include_archived:
        rows = db.rows(db.connect().execute("SELECT * FROM voices ORDER BY created_at DESC"))
    else:
        rows = db.rows(db.connect().execute("SELECT * FROM voices WHERE archived=0 ORDER BY created_at DESC"))
    return [_hydrate(r) for r in rows]


def delete(voice_id: str) -> bool:
    with db.tx() as conn:
        cur = conn.execute("DELETE FROM voices WHERE id=?", (voice_id,))
        return cur.rowcount > 0


def set_archived(voice_id: str, archived: bool) -> dict | None:
    with db.tx() as conn:
        conn.execute("UPDATE voices SET archived=? WHERE id=?", (int(archived), voice_id))
    return get(voice_id)


def resolve_audio(voice_id: str) -> dict | None:
    """把音色解析为音频记录（存在且未归档）。"""
    v = get(voice_id)
    if not v or v["archived"]:
        return None
    return db.get_audio(v["audio_id"])