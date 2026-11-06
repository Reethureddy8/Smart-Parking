"""SQLite storage. Timestamps are UNIX epoch seconds (UTC); the browser localises."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','operator')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL UNIQUE,
    row_idx INTEGER NOT NULL,
    col_idx INTEGER NOT NULL,
    x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL, y2 REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'standard' CHECK (kind IN ('standard','ev','accessible','large','bike')),
    enabled INTEGER NOT NULL DEFAULT 1,
    cam_state TEXT NOT NULL DEFAULT 'unknown' CHECK (cam_state IN ('unknown','free','car')),
    cam_conf REAL,
    cam_at INTEGER
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    plate TEXT NOT NULL,
    vehicle_class TEXT NOT NULL,
    slot_id INTEGER REFERENCES slots(id) ON DELETE SET NULL,
    slot_label TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('parked','closed','void')),
    entry_at INTEGER NOT NULL,
    exit_at INTEGER,
    fare REAL,
    pay_method TEXT,
    entry_image TEXT,
    ocr_conf REAL,
    accessible INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    closed_by INTEGER REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS ix_tickets_plate ON tickets(plate);
CREATE INDEX IF NOT EXISTS ix_tickets_exit ON tickets(exit_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_parked_plate ON tickets(plate) WHERE status = 'parked';
CREATE UNIQUE INDEX IF NOT EXISTS ux_parked_slot ON tickets(slot_id) WHERE status = 'parked';
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    ticket_id INTEGER,
    user_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_activity_at ON activity(at);
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    image TEXT NOT NULL,
    cars INTEGER NOT NULL,
    free INTEGER NOT NULL,
    stray INTEGER NOT NULL,
    user_id INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """One write transaction; IMMEDIATE so slot assignment can't race."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def read() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init() -> None:
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def now() -> int:
    return int(time.time())


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def one(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))


def log(conn: sqlite3.Connection, kind: str, message: str, ticket_id: int | None = None,
        user_id: int | None = None) -> None:
    conn.execute("INSERT INTO activity(at, kind, message, ticket_id, user_id) VALUES (?,?,?,?,?)",
                 (now(), kind, message, ticket_id, user_id))
