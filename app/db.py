# -*- coding: utf-8 -*-
"""Tiny SQLite store for settings and scrape jobs."""
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from app.config import DB_PATH, DEFAULTS, ensure_dirs

_lock = threading.RLock()
_conn = None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _get_conn():
    global _conn
    if _conn is None:
        ensure_dirs()
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def init_db():
    with _lock:
        conn = _get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                posts_limit INTEGER NOT NULL,
                days INTEGER NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'web',
                kind TEXT NOT NULL DEFAULT 'posts',
                chat_id TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                post_count INTEGER DEFAULT 0,
                oldest TEXT,
                newest TEXT,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                profile_name TEXT,
                error TEXT,
                analysis TEXT,
                result_path TEXT,
                log_path TEXT
            );
            """
        )
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        for column in ("oldest", "newest", "kind", "analysis"):
            if column not in existing:
                default = " NOT NULL DEFAULT 'posts'" if column == "kind" else ""
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT{default}")
        conn.commit()


def get_setting(key, default=None):
    with _lock:
        row = _get_conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return DEFAULTS.get(key, default)
    return row["value"]


def set_setting(key, value):
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        conn.commit()


def all_settings():
    with _lock:
        rows = _get_conn().execute("SELECT key, value FROM settings").fetchall()
    data = dict(DEFAULTS)
    data.update({r["key"]: r["value"] for r in rows if not r["key"].startswith("_")})
    return data


def create_job(target, posts_limit, days, source="web", chat_id=None, kind="posts"):
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO jobs(id, target, posts_limit, days, status, source, kind, chat_id, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, target, int(posts_limit), int(days), "queued", source, kind, chat_id, _now()),
        )
        conn.commit()
    return get_job(job_id)


def update_job(job_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        conn = _get_conn()
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))
        conn.commit()


def get_job(job_id):
    with _lock:
        row = _get_conn().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit=50, status=None):
    with _lock:
        conn = _get_conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def queue_position(job_id):
    with _lock:
        rows = _get_conn().execute(
            "SELECT id FROM jobs WHERE status IN ('queued','running') ORDER BY created_at ASC"
        ).fetchall()
    ids = [r["id"] for r in rows]
    return ids.index(job_id) + 1 if job_id in ids else 0
