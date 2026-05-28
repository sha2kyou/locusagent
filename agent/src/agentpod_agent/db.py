"""容器内 SQLite：memory / sessions / messages 表，WAL + sqlite-vec。

所有写入由"单 writer 队列"集中协调，避免并发写锁；读取可直接连接。
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

import sqlite_vec

from .config import get_settings
from .logging import get_logger

T = TypeVar("T")
log = get_logger("db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content         TEXT NOT NULL,
    anchor          TEXT NOT NULL DEFAULT 'experience',
    embedding       BLOB,
    embedding_state TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_memory_state ON memory(embedding_state);

CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    title        TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    total_tokens INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at   TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    tool_calls    TEXT,
    tool_call_id  TEXT,
    run_id        TEXT,
    tokens        INTEGER,
    created_at    TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS runs (
    id                   TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'running',
    assistant_message_id INTEGER,
    error_message        TEXT,
    created_at           TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at           TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS responses (
    id                   TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL,
    run_id               TEXT,
    previous_response_id TEXT,
    assistant_message_id INTEGER,
    model                TEXT,
    input_text           TEXT NOT NULL DEFAULT '',
    output_text          TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'completed',
    created_at           TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at           TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_responses_session ON responses(session_id, created_at DESC);
"""


def _db_path() -> Path:
    return get_settings().data_dir / "agent.sqlite"


def _open_conn(load_vec: bool = True) -> sqlite3.Connection:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    if load_vec:
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
    return conn


@contextmanager
def conn_scope(load_vec: bool = True):
    conn = _open_conn(load_vec=load_vec)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with conn_scope(load_vec=False) as c:
        for stmt in SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                c.execute(stmt)
        # 兼容老库：若 memory.anchor 不存在则补充（SQLite 无 IF NOT EXISTS 列语法）
        cols = c.execute("PRAGMA table_info(memory)").fetchall()
        col_names = {str(r["name"]) for r in cols}
        if "anchor" not in col_names:
            c.execute("ALTER TABLE memory ADD COLUMN anchor TEXT NOT NULL DEFAULT 'experience'")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_anchor ON memory(anchor)")
        msg_cols = {str(r["name"]) for r in c.execute("PRAGMA table_info(messages)").fetchall()}
        if "tool_call_id" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN tool_call_id TEXT")
        if "run_id" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN run_id TEXT")
        for stmt in (
            """
            CREATE TABLE IF NOT EXISTS runs (
                id                   TEXT PRIMARY KEY,
                session_id           TEXT NOT NULL,
                status               TEXT NOT NULL DEFAULT 'running',
                assistant_message_id INTEGER,
                error_message        TEXT,
                created_at           TIMESTAMP NOT NULL DEFAULT (datetime('now')),
                updated_at           TIMESTAMP NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, updated_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS responses (
                id                   TEXT PRIMARY KEY,
                session_id           TEXT NOT NULL,
                run_id               TEXT,
                previous_response_id TEXT,
                assistant_message_id INTEGER,
                model                TEXT,
                input_text           TEXT NOT NULL DEFAULT '',
                output_text          TEXT NOT NULL DEFAULT '',
                status               TEXT NOT NULL DEFAULT 'completed',
                created_at           TIMESTAMP NOT NULL DEFAULT (datetime('now')),
                updated_at           TIMESTAMP NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_responses_session ON responses(session_id, created_at DESC)",
        ):
            c.execute(stmt)
    log.info("agent_db_ready", path=str(_db_path()))


async def run_in_thread(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    return await asyncio.to_thread(func, *args, **kwargs)


async def run_async(func: Callable[..., Awaitable[T]]) -> T:
    return await func()
