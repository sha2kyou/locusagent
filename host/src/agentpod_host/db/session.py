"""异步 SQLite 引擎与会话管理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..config import get_settings
from .legacy import repair_legacy_bigint_autoincrement
from .models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_engine_db_path: Path | None = None


def _sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


async def init_engine() -> AsyncEngine:
    global _engine, _sessionmaker, _engine_db_path

    settings = get_settings()
    db_path = Path(settings.host_sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if _engine is not None and _engine_db_path == db_path:
        return _engine

    if _engine is not None:
        await dispose_engine()

    _engine = create_async_engine(
        _sqlite_url(db_path),
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    _engine_db_path = db_path

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(repair_legacy_bigint_autoincrement)

    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker, _engine_db_path
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
    _engine_db_path = None


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
