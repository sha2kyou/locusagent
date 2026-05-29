"""容器内 SQLite：memory / sessions / messages 表，WAL + sqlite-vec。

并发模型：每次操作经 ``asyncio.to_thread`` 在线程池中用独立短连接执行，写并发
依赖 WAL(单写多读)+ ``busy_timeout`` 排队等待，而非应用层写队列。单用户容器内
并发量低，足够；如未来出现写争用再引入显式写串行。
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
    id            TEXT PRIMARY KEY,
    title         TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    total_tokens  INTEGER NOT NULL DEFAULT 0,
    system_prompt TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at    TIMESTAMP NOT NULL DEFAULT (datetime('now'))
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

CREATE TABLE IF NOT EXISTS artifact_categories (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifacts (
    id              TEXT PRIMARY KEY,
    category_id     TEXT,
    type            TEXT NOT NULL DEFAULT 'text',
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    embedding       BLOB,
    embedding_state TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at      TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_artifacts_category ON artifacts(category_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_embed_state ON artifacts(embedding_state);

CREATE TABLE IF NOT EXISTS env_vars (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    value           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    embedding       BLOB,
    embedding_state TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at      TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_env_vars_name ON env_vars(name);
CREATE INDEX IF NOT EXISTS idx_env_vars_embed_state ON env_vars(embedding_state);
"""


_MESSAGES_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


def _init_messages_fts(c: sqlite3.Connection) -> None:
    """为 messages.content 建 trigram FTS5（external content）+ 同步触发器。

    仅首次创建时回填一次；环境不支持 FTS5/trigram 时降级（不建表，检索回退 LIKE）。
    """
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages_fts'"
    ).fetchone()
    if exists:
        return
    try:
        c.execute(
            "CREATE VIRTUAL TABLE messages_fts USING fts5("
            "content, content='messages', content_rowid='id', tokenize='trigram')"
        )
        c.executescript(_MESSAGES_FTS_TRIGGERS)
        c.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
        log.info("messages_fts_ready")
    except sqlite3.OperationalError as exc:
        log.warning("messages_fts_unavailable", error=str(exc))


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
    # 并行工具可能并发写：让写锁等待而非立即抛 "database is locked"
    conn.execute("PRAGMA busy_timeout=10000")
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
        sess_cols = {str(r["name"]) for r in c.execute("PRAGMA table_info(sessions)").fetchall()}
        if "system_prompt" not in sess_cols:
            c.execute("ALTER TABLE sessions ADD COLUMN system_prompt TEXT")
        art_cols = {str(r["name"]) for r in c.execute("PRAGMA table_info(artifacts)").fetchall()}
        if art_cols and "type" not in art_cols:
            c.execute("ALTER TABLE artifacts ADD COLUMN type TEXT NOT NULL DEFAULT 'text'")
        if art_cols and "embedding" not in art_cols:
            c.execute("ALTER TABLE artifacts ADD COLUMN embedding BLOB")
        if art_cols and "embedding_state" not in art_cols:
            c.execute(
                "ALTER TABLE artifacts ADD COLUMN embedding_state TEXT NOT NULL DEFAULT 'pending'"
            )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifacts_embed_state ON artifacts(embedding_state)"
        )
        env_cols = {str(r["name"]) for r in c.execute("PRAGMA table_info(env_vars)").fetchall()}
        if env_cols and "description" not in env_cols:
            c.execute("ALTER TABLE env_vars ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if env_cols and "embedding" not in env_cols:
            c.execute("ALTER TABLE env_vars ADD COLUMN embedding BLOB")
        if env_cols and "embedding_state" not in env_cols:
            c.execute(
                "ALTER TABLE env_vars ADD COLUMN embedding_state TEXT NOT NULL DEFAULT 'pending'"
            )
        if env_cols and "updated_at" not in env_cols:
            c.execute(
                "ALTER TABLE env_vars ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT (datetime('now'))"
            )
        c.execute("CREATE INDEX IF NOT EXISTS idx_env_vars_name ON env_vars(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_env_vars_embed_state ON env_vars(embedding_state)")
        _init_messages_fts(c)
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
