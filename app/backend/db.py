"""SQLite 持久化：音频文件、任务、worker 状态、控制标志、设置。WAL 模式，多线程安全。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS audio_files (
    id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    normalized_path TEXT,
    format TEXT,
    sample_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    duration REAL,
    size_bytes INTEGER,
    sha256 TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    audio_id TEXT NOT NULL REFERENCES audio_files(id),
    mode TEXT NOT NULL DEFAULT 'replace',
    original_text TEXT DEFAULT '',
    target_text TEXT DEFAULT '',
    segment_json TEXT DEFAULT '',
    instruction TEXT DEFAULT '',
    final_instruction TEXT DEFAULT '',
    model_variant TEXT NOT NULL DEFAULT 'flash',
    bits INTEGER,
    sequential INTEGER NOT NULL DEFAULT 0,
    seed INTEGER,
    gen_seconds REAL,
    nfe INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    stage_detail TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    elapsed_s REAL,
    output_path TEXT,
    output_duration REAL,
    accepted INTEGER,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    peak_memory_gb REAL,
    rtf REAL,
    kind TEXT NOT NULL DEFAULT 'infer',
    voice_id TEXT,
    description TEXT DEFAULT '',
    emotion TEXT DEFAULT '',
    install_json TEXT DEFAULT '',
    note TEXT DEFAULT '',
    model_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    audio_id TEXT,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    label TEXT DEFAULT '',
    created_at REAL NOT NULL,
    rating INTEGER,
    favorite INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS worker_state (
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
    device TEXT DEFAULT '',
    mlx_available INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS control (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    unload_requested INTEGER NOT NULL DEFAULT 0,
    updated_at REAL,
    activate_variant TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    tags_json TEXT DEFAULT '[]',
    audio_id TEXT NOT NULL,
    source TEXT DEFAULT 'upload',
    consent_json TEXT DEFAULT '',
    allowed_use TEXT DEFAULT '',
    job_id TEXT,
    created_at REAL NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'auk_remote',
    base_url TEXT NOT NULL,
    api_key TEXT DEFAULT '',
    model TEXT DEFAULT '',
    voice TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        _local.conn = conn
    return conn


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    with tx() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO worker_state (id, model_loaded) VALUES (1, 0)")
        conn.execute("INSERT OR IGNORE INTO control (id, unload_requested) VALUES (1, 0)")
        # 轻量迁移：为旧数据库补充新增列（只增不删，BASELINE §5）
        migrations = (
            "ALTER TABLE jobs ADD COLUMN nfe INTEGER",
            "ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'infer'",
            "ALTER TABLE jobs ADD COLUMN voice_id TEXT",
            "ALTER TABLE jobs ADD COLUMN description TEXT DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN emotion TEXT DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN install_json TEXT DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN note TEXT DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN model_id TEXT",
            "ALTER TABLE jobs ADD COLUMN provider_id TEXT",
            "ALTER TABLE files ADD COLUMN rating INTEGER",
            "ALTER TABLE files ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE control ADD COLUMN activate_variant TEXT",
            # 跨平台：MLX 可用性（worker 启动探针写入；默认 0=不可用，保守）
            "ALTER TABLE worker_state ADD COLUMN mlx_available INTEGER DEFAULT 0",
        )
        for ddl in migrations:
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass  # 列已存在
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs(kind)")


def rows(cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cursor.fetchall()]


def one(cursor) -> dict[str, Any] | None:
    r = cursor.fetchone()
    return dict(r) if r else None


# ---------------- audio files ----------------

def insert_audio(meta: dict) -> dict:
    meta.setdefault("id", new_id("aud"))
    meta.setdefault("created_at", time.time())
    with tx() as conn:
        conn.execute(
            """INSERT INTO audio_files (id, original_name, stored_path, normalized_path, format,
               sample_rate, channels, bit_depth, duration, size_bytes, sha256, created_at)
               VALUES (:id, :original_name, :stored_path, :normalized_path, :format,
               :sample_rate, :channels, :bit_depth, :duration, :size_bytes, :sha256, :created_at)""",
            meta,
        )
    return meta


def get_audio(audio_id: str) -> dict | None:
    return one(connect().execute("SELECT * FROM audio_files WHERE id=?", (audio_id,)))


def list_audio() -> list[dict]:
    return rows(connect().execute("SELECT * FROM audio_files ORDER BY created_at DESC"))


def delete_audio(audio_id: str) -> None:
    with tx() as conn:
        conn.execute("DELETE FROM audio_files WHERE id=?", (audio_id,))


# ---------------- files (download registry) ----------------

def register_file(path: str, kind: str, *, job_id: str | None = None, audio_id: str | None = None,
                  label: str = "", file_id: str | None = None) -> str:
    fid = file_id or new_id("file")
    with tx() as conn:
        conn.execute(
            "INSERT INTO files (id, job_id, audio_id, kind, path, label, created_at) VALUES (?,?,?,?,?,?,?)",
            (fid, job_id, audio_id, kind, str(path), label, time.time()),
        )
    return fid


def get_file(file_id: str) -> dict | None:
    return one(connect().execute("SELECT * FROM files WHERE id=?", (file_id,)))


# ---------------- jobs ----------------

JOB_FIELDS = (
    "audio_id mode original_text target_text segment_json instruction final_instruction "
    "model_variant bits sequential seed gen_seconds nfe kind voice_id description emotion "
    "note model_id provider_id"
).split()


def insert_job(data: dict) -> dict:
    job = {k: data.get(k) for k in JOB_FIELDS}
    job.update(
        id=new_id("job"), status="queued", stage_detail="", error="",
        created_at=time.time(), started_at=None, finished_at=None, elapsed_s=None,
        output_path=None, output_duration=None, accepted=None, cancel_requested=0,
        peak_memory_gb=None, rtf=None, install_json="",
    )
    job.setdefault("kind", "infer")
    job["kind"] = job.get("kind") or "infer"
    job["model_variant"] = job.get("model_variant") or "flash"
    job["sequential"] = int(job.get("sequential") or 0)
    job["description"] = job.get("description") or ""
    job["emotion"] = job.get("emotion") or ""
    job["note"] = job.get("note") or ""
    # audio_id 对 instruct_tts 可空：DB 列 NOT NULL，存 ""，API 层返回 null
    job["audio_id"] = job.get("audio_id") or ""
    job["segment_json"] = json.dumps(job.get("segment_json") or {}, ensure_ascii=False)
    with tx() as conn:
        cols = ", ".join(job.keys())
        ph = ", ".join(f":{k}" for k in job)
        conn.execute(f"INSERT INTO jobs ({cols}) VALUES ({ph})", job)
    return job


def _hydrate_job(j: dict) -> dict:
    if j.get("segment_json"):
        try:
            j["segment"] = json.loads(j["segment_json"])
        except json.JSONDecodeError:
            j["segment"] = {}
    ij = j.get("install_json")
    if isinstance(ij, str) and ij:
        try:
            j["install_json"] = json.loads(ij)
        except json.JSONDecodeError:
            j["install_json"] = None
    elif not ij:
        j["install_json"] = None
    if j.get("audio_id") == "":
        j["audio_id"] = None
    return j


def get_job(job_id: str) -> dict | None:
    j = one(connect().execute("SELECT * FROM jobs WHERE id=?", (job_id,)))
    return _hydrate_job(j) if j else None


def list_jobs(limit: int = 200, status: str | None = None, kind: str | None = None) -> list[dict]:
    where, params = [], []
    if status:
        where.append("status=?")
        params.append(status)
    if kind:
        where.append("kind=?")
        params.append(kind)
    sql = "SELECT * FROM jobs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    return [_hydrate_job(j) for j in rows(connect().execute(sql, (*params, limit)))]


def count_active_jobs() -> int:
    running = ("queued", "preparing", "loading_model", "processing", "postprocessing")
    row = one(connect().execute(
        f"SELECT COUNT(*) AS n FROM jobs WHERE status IN ({','.join('?' * len(running))})", running))
    return int(row["n"]) if row else 0


def active_model_job(model_id: str) -> dict | None:
    """该模型最近一个未终态的 install/verify 任务。"""
    running = ("queued", "preparing", "loading_model", "processing", "postprocessing")
    return one(connect().execute(
        f"SELECT * FROM jobs WHERE model_id=? AND kind IN ('install','verify') "
        f"AND status IN ({','.join('?' * len(running))}) ORDER BY created_at DESC LIMIT 1",
        (model_id, *running)))


def last_model_job(model_id: str, kind: str) -> dict | None:
    return one(connect().execute(
        "SELECT * FROM jobs WHERE model_id=? AND kind=? ORDER BY created_at DESC LIMIT 1",
        (model_id, kind)))


def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with tx() as conn:
        conn.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))


def claim_next_job(worker_pid: int) -> dict | None:
    """原子领取最早的 queued 任务（单 worker，但用条件更新防重）。"""
    conn = connect()
    with tx():
        row = one(conn.execute(
            "SELECT id FROM jobs WHERE status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1"))
        if not row:
            return None
        cur = conn.execute(
            "UPDATE jobs SET status='preparing', started_at=?, stage_detail='准备输入' "
            "WHERE id=? AND status='queued'", (time.time(), row["id"]))
        if cur.rowcount == 0:
            return None
    return get_job(row["id"])


def mark_interrupted_jobs() -> int:
    """启动时把遗留的运行中任务标记为 failed（可重试）。"""
    running = ("preparing", "loading_model", "processing", "postprocessing")
    with tx() as conn:
        cur = conn.execute(
            f"UPDATE jobs SET status='failed', error='应用上次异常退出，任务被中断（interrupted），可重试', "
            f"finished_at=? WHERE status IN ({','.join('?' * len(running))})",
            (time.time(), *running))
        return cur.rowcount


# ---------------- worker / control ----------------

def worker_heartbeat(pid: int, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    with tx() as conn:
        conn.execute(
            f"UPDATE worker_state SET pid=?, heartbeat=?{', ' + sets if sets else ''} WHERE id=1",
            (pid, time.time(), *fields.values()))


def get_worker_state() -> dict | None:
    return one(connect().execute("SELECT * FROM worker_state WHERE id=1"))


def request_unload() -> None:
    with tx() as conn:
        conn.execute("UPDATE control SET unload_requested=1, updated_at=? WHERE id=1", (time.time(),))


def consume_unload_request() -> bool:
    conn = connect()
    with tx():
        row = one(conn.execute("SELECT unload_requested FROM control WHERE id=1"))
        if row and row["unload_requested"]:
            conn.execute("UPDATE control SET unload_requested=0, updated_at=? WHERE id=1", (time.time(),))
            return True
    return False


def request_activate(variant: str) -> None:
    with tx() as conn:
        conn.execute("UPDATE control SET activate_variant=?, updated_at=? WHERE id=1", (variant, time.time()))


def consume_activate_request() -> str | None:
    conn = connect()
    with tx():
        row = one(conn.execute("SELECT activate_variant FROM control WHERE id=1"))
        if row and row["activate_variant"]:
            conn.execute("UPDATE control SET activate_variant=NULL, updated_at=? WHERE id=1", (time.time(),))
            return row["activate_variant"]
    return None


# ---------------- files rating ----------------

def rate_file(file_id: str, rating: int | None, favorite: bool | None) -> dict | None:
    f = get_file(file_id)
    if not f:
        return None
    fields = {}
    if rating is not None:
        fields["rating"] = rating
    if favorite is not None:
        fields["favorite"] = int(favorite)
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        with tx() as conn:
            conn.execute(f"UPDATE files SET {sets} WHERE id=?", (*fields.values(), file_id))
    return get_file(file_id)


# ---------------- settings ----------------

DEFAULT_SETTINGS = {
    "theme": "light",
    "crossfade_ms": str(config.DEFAULT_CROSSFADE_MS),
    "default_bits": str(config.DEFAULT_BITS),
    "default_sequential": "1" if config.DEFAULT_SEQUENTIAL else "0",
    "idle_unload_s": str(config.MODEL_IDLE_UNLOAD_S),
    "language": "zh-CN",
    "allow_update_check": "0",
    "default_variant": "flash",
}


def get_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    for r in connect().execute("SELECT key, value FROM settings"):
        out[r["key"]] = r["value"]
    return out


def set_settings(values: dict) -> dict:
    with tx() as conn:
        for k, v in values.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)))
    return get_settings()