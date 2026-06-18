"""Agent 内 SQLite：memory / sessions / messages 表，WAL + sqlite-vec。

并发模型：每次操作经 ``asyncio.to_thread`` 在线程池中用独立短连接执行，写并发
依赖 WAL（单写多读）与 ``busy_timeout`` 排队等待，而非应用层写队列。
"""

from __future__ import annotations

import asyncio
import contextvars
import sqlite3
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

import sqlite_vec

from .logging import get_logger
from .workspace import workspace_data_dir

T = TypeVar("T")
log = get_logger("db")

_DB_THREAD_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="locusagent-db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content         TEXT NOT NULL,
    anchor          TEXT NOT NULL DEFAULT 'experience',
    origin          TEXT NOT NULL DEFAULT 'manual',
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
    hidden        INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at    TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    reasoning_content TEXT NOT NULL DEFAULT '',
    tool_calls    TEXT,
    tool_call_id  TEXT,
    run_id        TEXT,
    tokens        INTEGER,
    embedding     BLOB,
    context_state TEXT NOT NULL DEFAULT 'active',
    archive_batch_id TEXT,
    archived_at   TIMESTAMP,
    embedding_state TEXT NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_context ON messages(session_id, context_state, id);
CREATE INDEX IF NOT EXISTS idx_messages_embed_state ON messages(embedding_state);

CREATE TABLE IF NOT EXISTS attachments (
    id               TEXT PRIMARY KEY,
    session_id       TEXT,
    kind             TEXT NOT NULL,
    name             TEXT NOT NULL,
    mime_type        TEXT,
    size_bytes       INTEGER NOT NULL DEFAULT 0,
    object_key       TEXT,
    object_etag      TEXT,
    sha256           TEXT,
    processable      INTEGER NOT NULL DEFAULT 1,
    unsupported_reason TEXT,
    truncated        INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_attachments_session ON attachments(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attachments_sha256 ON attachments(sha256, kind);


CREATE TABLE IF NOT EXISTS message_attachments (
    message_id       INTEGER NOT NULL,
    attachment_id    TEXT NOT NULL,
    order_index      INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (message_id, attachment_id)
);
CREATE INDEX IF NOT EXISTS idx_message_attachments_message ON message_attachments(message_id, order_index);
CREATE INDEX IF NOT EXISTS idx_message_attachments_attachment ON message_attachments(attachment_id);

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

CREATE TABLE IF NOT EXISTS artifact_categories (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifacts (
    id              TEXT PRIMARY KEY,
    category_id     TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS session_todos (
    session_id  TEXT PRIMARY KEY,
    plan_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    steps_json  TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at  TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
"""


_MESSAGES_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""

_MEMORY_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS memory_fts_ai AFTER INSERT ON memory BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memory_fts_ad AFTER DELETE ON memory BEGIN
    DELETE FROM memory_fts WHERE rowid = old.id;
END;
CREATE TRIGGER IF NOT EXISTS memory_fts_au AFTER UPDATE ON memory BEGIN
    DELETE FROM memory_fts WHERE rowid = old.id;
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;
"""

_ENV_VARS_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS env_vars_fts_ai AFTER INSERT ON env_vars BEGIN
    INSERT INTO env_vars_fts(rowid, name, description) VALUES (new.id, new.name, new.description);
END;
CREATE TRIGGER IF NOT EXISTS env_vars_fts_ad AFTER DELETE ON env_vars BEGIN
    DELETE FROM env_vars_fts WHERE rowid = old.id;
END;
CREATE TRIGGER IF NOT EXISTS env_vars_fts_au AFTER UPDATE ON env_vars BEGIN
    DELETE FROM env_vars_fts WHERE rowid = old.id;
    INSERT INTO env_vars_fts(rowid, name, description) VALUES (new.id, new.name, new.description);
END;
"""

_ARTIFACTS_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS artifacts_fts_ai AFTER INSERT ON artifacts BEGIN
    INSERT INTO artifacts_fts(rowid, title, content, artifact_id) VALUES (new.rowid, new.title, new.content, new.id);
END;
CREATE TRIGGER IF NOT EXISTS artifacts_fts_ad AFTER DELETE ON artifacts BEGIN
    DELETE FROM artifacts_fts WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS artifacts_fts_au AFTER UPDATE ON artifacts BEGIN
    DELETE FROM artifacts_fts WHERE rowid = old.rowid;
    INSERT INTO artifacts_fts(rowid, title, content, artifact_id) VALUES (new.rowid, new.title, new.content, new.id);
END;
"""


def _drop_fts_triggers(c: sqlite3.Connection) -> None:
    for name in (
        "messages_fts_ai",
        "messages_fts_ad",
        "messages_fts_au",
        "memory_fts_ai",
        "memory_fts_ad",
        "memory_fts_au",
        "env_vars_fts_ai",
        "env_vars_fts_ad",
        "env_vars_fts_au",
        "artifacts_fts_ai",
        "artifacts_fts_ad",
        "artifacts_fts_au",
    ):
        c.execute(f"DROP TRIGGER IF EXISTS {name}")


def _table_exists(c: sqlite3.Connection, name: str) -> bool:
    row = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _restore_fts_triggers(c: sqlite3.Connection) -> None:
    if _table_exists(c, "messages_fts"):
        c.executescript(_MESSAGES_FTS_TRIGGERS)
    if _table_exists(c, "memory_fts"):
        c.executescript(_MEMORY_FTS_TRIGGERS)
    if _table_exists(c, "env_vars_fts"):
        c.executescript(_ENV_VARS_FTS_TRIGGERS)
    if _table_exists(c, "artifacts_fts"):
        c.executescript(_ARTIFACTS_FTS_TRIGGERS)


def _init_messages_fts(c: sqlite3.Connection) -> None:
    """为 messages.content 建 trigram FTS5（standalone + trigger，与其他表一致）。"""
    row = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='messages_fts'"
    ).fetchone()
    if row:
        ddl = str(row[0] or "")
        if "content='messages'" in ddl:
            _migrate_messages_fts_to_standalone(c)
        return
    try:
        c.execute(
            "CREATE VIRTUAL TABLE messages_fts USING fts5(content, tokenize='trigram')"
        )
        c.executescript(_MESSAGES_FTS_TRIGGERS)
        c.execute("INSERT INTO messages_fts(rowid, content) SELECT id, content FROM messages")
        log.info("messages_fts_ready")
    except sqlite3.OperationalError as exc:
        log.warning("messages_fts_unavailable", error=str(exc))


def _migrate_messages_fts_to_standalone(c: sqlite3.Connection) -> None:
    """将旧版 external-content messages_fts 迁移为 standalone。"""
    try:
        for name in ("messages_fts_ai", "messages_fts_ad", "messages_fts_au"):
            c.execute(f"DROP TRIGGER IF EXISTS {name}")
        c.execute("DROP TABLE IF EXISTS messages_fts")
        c.execute(
            "CREATE VIRTUAL TABLE messages_fts USING fts5(content, tokenize='trigram')"
        )
        c.executescript(_MESSAGES_FTS_TRIGGERS)
        c.execute("INSERT INTO messages_fts(rowid, content) SELECT id, content FROM messages")
        log.info("messages_fts_migrated_standalone")
    except sqlite3.OperationalError as exc:
        log.warning("messages_fts_migration_failed", error=str(exc))


def _init_memory_fts(c: sqlite3.Connection) -> None:
    if c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_fts'"
    ).fetchone():
        return
    try:
        c.execute(
            "CREATE VIRTUAL TABLE memory_fts USING fts5(content, tokenize='trigram')"
        )
        c.executescript(_MEMORY_FTS_TRIGGERS)
        c.execute(
            "INSERT INTO memory_fts(rowid, content) SELECT id, content FROM memory"
        )
        log.info("memory_fts_ready")
    except sqlite3.OperationalError as exc:
        log.warning("memory_fts_unavailable", error=str(exc))


def _init_env_vars_fts(c: sqlite3.Connection) -> None:
    if c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='env_vars_fts'"
    ).fetchone():
        return
    try:
        c.execute(
            "CREATE VIRTUAL TABLE env_vars_fts USING fts5("
            "name, description, tokenize='trigram')"
        )
        c.executescript(_ENV_VARS_FTS_TRIGGERS)
        c.execute(
            "INSERT INTO env_vars_fts(rowid, name, description) "
            "SELECT id, name, description FROM env_vars"
        )
        log.info("env_vars_fts_ready")
    except sqlite3.OperationalError as exc:
        log.warning("env_vars_fts_unavailable", error=str(exc))


def _init_artifacts_fts(c: sqlite3.Connection) -> None:
    if c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifacts_fts'"
    ).fetchone():
        return
    try:
        c.execute(
            "CREATE VIRTUAL TABLE artifacts_fts USING fts5("
            "title, content, artifact_id UNINDEXED, tokenize='trigram')"
        )
        c.executescript(_ARTIFACTS_FTS_TRIGGERS)
        c.execute(
            "INSERT INTO artifacts_fts(rowid, title, content, artifact_id) "
            "SELECT rowid, title, content, id FROM artifacts"
        )
        log.info("artifacts_fts_ready")
    except sqlite3.OperationalError as exc:
        log.warning("artifacts_fts_unavailable", error=str(exc))


def _db_path() -> Path:
    return workspace_data_dir() / "agent.sqlite"


def _open_conn(load_vec: bool = True) -> sqlite3.Connection:
    workspace_data_dir()
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


def _column_exists(c: sqlite3.Connection, table: str, column: str) -> bool:
    rows = c.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _ensure_memory_origin_column(c: sqlite3.Connection) -> None:
    if not _column_exists(c, "memory", "origin"):
        c.execute("ALTER TABLE memory ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")
        log.info("memory_origin_column_added")


def _ensure_sessions_hidden_column(c: sqlite3.Connection) -> None:
    if not _column_exists(c, "sessions", "hidden"):
        c.execute("ALTER TABLE sessions ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
        log.info("sessions_hidden_column_added")


def _ensure_attachments_file_sha256_column(c: sqlite3.Connection) -> None:
    if not _column_exists(c, "attachments", "file_sha256"):
        c.execute("ALTER TABLE attachments ADD COLUMN file_sha256 TEXT")
        log.info("attachments_file_sha256_column_added")


def _ensure_sessions_review_state_column(c: sqlite3.Connection) -> None:
    if not _column_exists(c, "sessions", "review_state"):
        c.execute("ALTER TABLE sessions ADD COLUMN review_state TEXT")
        log.info("sessions_review_state_column_added")


def init_db() -> None:
    with conn_scope(load_vec=False) as c:
        for stmt in SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                c.execute(stmt)
        # 兼容历史坏触发器：先清掉，避免迁移期间 UPDATE 触发 SQL logic error。
        _drop_fts_triggers(c)
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_anchor ON memory(anchor)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_sha256 ON attachments(sha256, kind)"
        )
        _ensure_memory_origin_column(c)
        _ensure_attachments_file_sha256_column(c)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_file_sha256 ON attachments(file_sha256)"
        )
        _ensure_sessions_hidden_column(c)
        _ensure_sessions_review_state_column(c)
        if _table_exists(c, "artifacts"):
            deleted = c.execute(
                "DELETE FROM artifacts WHERE category_id IS NULL "
                "OR category_id NOT IN (SELECT id FROM artifact_categories)"
            ).rowcount
            if deleted:
                log.info("artifacts_orphans_purged", count=deleted)
        c.execute(
            "UPDATE messages SET embedding_state='skipped' "
            "WHERE embedding_state IN ('pending', 'failed') "
            "AND role NOT IN ('user', 'assistant')"
        )
        c.execute(
            "UPDATE messages SET embedding_state='pending' WHERE embedding_state='failed'"
        )
        c.execute(
            "UPDATE memory SET embedding_state='pending' WHERE embedding_state='failed'"
        )
        c.execute(
            "UPDATE artifacts SET embedding_state='pending' WHERE embedding_state='failed'"
        )
        _init_messages_fts(c)
        _init_memory_fts(c)
        _init_env_vars_fts(c)
        _init_artifacts_fts(c)
        _restore_fts_triggers(c)
        c.execute('DROP TABLE IF EXISTS "responses"')
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
        ):
            c.execute(stmt)
    log.info("agent_db_ready", path=str(_db_path()))


async def run_in_thread(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run sync work in the DB thread pool, preserving caller contextvars (e.g. workspace_id)."""
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()

    def _run() -> T:
        if kwargs:
            return ctx.run(partial(func, *args, **kwargs))
        return ctx.run(func, *args)

    return await loop.run_in_executor(_DB_THREAD_POOL, _run)


def shutdown_db_thread_pool() -> None:
    _DB_THREAD_POOL.shutdown(wait=False, cancel_futures=True)


async def run_async(func: Callable[..., Awaitable[T]]) -> T:
    return await func()
