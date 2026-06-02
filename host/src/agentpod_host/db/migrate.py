"""启动时运行 Alembic 迁移。"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from ..logging import get_logger

log = get_logger("db.migrate")

INITIAL_REVISION = "001"


def _sync_database_url(database_url: str) -> str:
    if "+asyncpg" in database_url:
        return database_url.replace("+asyncpg", "+psycopg", 1)
    return database_url


def _alembic_dir() -> Path:
    """迁移脚本目录：优先使用包内路径，兼容本地 host/alembic 开发布局。"""
    here = Path(__file__).resolve().parent
    for candidate in (here / "alembic", here.parents[3] / "alembic"):
        if (candidate / "env.py").is_file():
            return candidate
    raise RuntimeError("alembic directory not found")


def _alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_alembic_dir()))
    cfg.set_main_option("sqlalchemy.url", _sync_database_url(database_url))
    return cfg


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :name
            """
        ),
        {"name": table_name},
    ).first()
    return row is not None


def _current_revision(conn) -> str | None:
    if not _table_exists(conn, "alembic_version"):
        return None
    row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
    if row is None:
        return None
    return str(row[0])


def _stamp_legacy_database(cfg: Config, database_url: str) -> None:
    """create_all 时代已有表但未写入 alembic_version 时，直接标记为 001。"""
    engine = create_engine(_sync_database_url(database_url), pool_pre_ping=True)
    with engine.connect() as conn:
        if _current_revision(conn) is not None:
            return
        if not _table_exists(conn, "users"):
            return
    log.info("alembic_stamp_legacy_database", revision=INITIAL_REVISION)
    command.stamp(cfg, INITIAL_REVISION)


def run_migrations(database_url: str) -> None:
    cfg = _alembic_config(database_url)
    _stamp_legacy_database(cfg, database_url)
    command.upgrade(cfg, "head")


def bootstrap_data(database_url: str) -> None:
    """迁移后的幂等数据/索引补齐（默认工作区、workspace_id 回填等）。"""
    engine = create_engine(_sync_database_url(database_url), pool_pre_ping=True)
    with engine.begin() as conn:
        if not _table_exists(conn, "users"):
            return
        conn.execute(
            text(
                """
                INSERT INTO workspaces (id, user_id, name, is_default)
                SELECT
                    'ws_' || substr(md5(random()::text || u.id::text), 1, 20),
                    u.id,
                    '默认工作区',
                    true
                FROM users u
                WHERE NOT EXISTS (
                    SELECT 1 FROM workspaces w WHERE w.user_id = u.id
                )
                """
            )
        )
        if _table_exists(conn, "scheduled_tasks"):
            conn.execute(
                text(
                    """
                    WITH default_ws AS (
                        SELECT DISTINCT ON (user_id) user_id, id
                        FROM workspaces
                        WHERE is_default = true
                        ORDER BY user_id, created_at ASC, id ASC
                    )
                    UPDATE scheduled_tasks st
                    SET workspace_id = d.id
                    FROM default_ws d
                    WHERE st.workspace_id IS NULL AND st.user_id = d.user_id
                    """
                )
            )
        if _table_exists(conn, "notifications"):
            conn.execute(
                text(
                    """
                    WITH default_ws AS (
                        SELECT DISTINCT ON (user_id) user_id, id
                        FROM workspaces
                        WHERE is_default = true
                        ORDER BY user_id, created_at ASC, id ASC
                    )
                    UPDATE notifications n
                    SET workspace_id = d.id
                    FROM default_ws d
                    WHERE n.workspace_id IS NULL AND n.user_id = d.user_id
                    """
                )
            )
        if _table_exists(conn, "workspaces"):
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_workspaces_user_default_true
                    ON workspaces(user_id) WHERE is_default = true
                    """
                )
            )


# 兼容旧调用名
seed_default_workspaces = bootstrap_data
