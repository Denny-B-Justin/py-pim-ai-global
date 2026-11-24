"""Process-shared state in SQLite: rate limits, login failures, background jobs."""
import json
import os
import sqlite3
import threading
import time

from constants import JOB_TTL_SECONDS, STATE_DB_PATH

_local = threading.local()
_init_lock = threading.Lock()
_ready = False

_DDL = (
    "CREATE TABLE IF NOT EXISTS hits (key TEXT NOT NULL, ts REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS hits_key ON hits (key, ts)",
    "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, ts REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)",
)


def _conn() -> sqlite3.Connection:
    global _ready
    con = getattr(_local, "con", None)
    if con is None:
        with _init_lock:
            new = not os.path.exists(STATE_DB_PATH)
            con = sqlite3.connect(STATE_DB_PATH, timeout=10, isolation_level=None)
            if new:
                os.chmod(STATE_DB_PATH, 0o600)
            con.execute("PRAGMA journal_mode=WAL")
            if not _ready:
                for stmt in _DDL:
                    con.execute(stmt)
                _ready = True
        _local.con = con
    return con


# ── Rate limiting / failure counters (sliding window) ────────────────────
def hit(key: str, limit: int, window_s: int) -> tuple[bool, int, int]:
    """Record a hit; return (allowed, remaining, retry_after_s)."""
    con, now = _conn(), time.time()
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("DELETE FROM hits WHERE key = ? AND ts < ?", (key, now - window_s))
        n, oldest = con.execute("SELECT COUNT(*), MIN(ts) FROM hits WHERE key = ?", (key,)).fetchone()
        if n >= limit:
            con.execute("COMMIT")
            return False, 0, max(1, int(oldest + window_s - now))
        con.execute("INSERT INTO hits (key, ts) VALUES (?, ?)", (key, now))
        con.execute("COMMIT")
        return True, limit - n - 1, window_s
    except Exception:
        con.execute("ROLLBACK")
        raise


def count(key: str, window_s: int) -> int:
    return _conn().execute("SELECT COUNT(*) FROM hits WHERE key = ? AND ts >= ?", (key, time.time() - window_s)).fetchone()[0]


def record(key: str) -> None:
    _conn().execute("INSERT INTO hits (key, ts) VALUES (?, ?)", (key, time.time()))


def clear(key: str) -> None:
    _conn().execute("DELETE FROM hits WHERE key = ?", (key,))


# ── Key/value (server-side admin sessions) ───────────────────────────────
def kv_set(key: str, value: dict) -> None:
    _conn().execute("INSERT OR REPLACE INTO kv (key, value, ts) VALUES (?, ?, ?)", (key, json.dumps(value), time.time()))


def kv_get(key: str) -> dict | None:
    row = _conn().execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def kv_del(key: str) -> None:
    _conn().execute("DELETE FROM kv WHERE key = ?", (key,))


# ── Jobs ─────────────────────────────────────────────────────────────────
def job_create(job_id: str, owner: str) -> None:
    con, now = _conn(), time.time()
    con.execute("DELETE FROM jobs WHERE created < ?", (now - JOB_TTL_SECONDS,))
    con.execute("DELETE FROM hits WHERE ts < ?", (now - 86400,))
    con.execute("DELETE FROM kv WHERE ts < ?", (now - 86400,))
    con.execute("INSERT INTO jobs (id, owner, created, status, payload) VALUES (?, ?, ?, 'running', '{}')", (job_id, owner, now))


def job_finish(job_id: str, status: str, payload: dict) -> None:
    _conn().execute("UPDATE jobs SET status = ?, payload = ? WHERE id = ?", (status, json.dumps(payload), job_id))


def job_get(job_id: str, owner: str) -> dict | None:
    """Return the job only if it belongs to `owner`."""
    row = _conn().execute("SELECT status, payload, created FROM jobs WHERE id = ? AND owner = ?", (job_id, owner)).fetchone()
    if not row:
        return None
    return {"status": row[0], "created": row[2], **json.loads(row[1])}
