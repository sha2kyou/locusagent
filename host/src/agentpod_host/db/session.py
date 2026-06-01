"""异步数据库引擎与会话管理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..config import get_settings
from .models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


async def init_engine() -> AsyncEngine:
    """启动时初始化引擎并 create_all。"""
    global _engine, _sessionmaker
    if _engine is not None:
        return _engine
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # P0 无迁移框架：在启动时补齐新增列，保证老库可用。
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tavily_api_key_enc BYTEA")
        )
        await conn.execute(
            text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS category VARCHAR(64)")
        )
        await conn.execute(
            text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64)")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC'")
        )
        await conn.execute(
            text("ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64)")
        )
        await conn.execute(
            text("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''")
        )
        await conn.execute(
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
        await conn.execute(
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
        await conn.execute(
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
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_workspaces_user_default_true "
                "ON workspaces(user_id) WHERE is_default = true"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_notifications_user_ws_created "
                "ON notifications(user_id, workspace_id, created_at)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_notifications_user_ws_unread "
                "ON notifications(user_id, workspace_id, read_at)"
            )
        )
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("数据库引擎未初始化，先调用 init_engine()")
    async with _sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
