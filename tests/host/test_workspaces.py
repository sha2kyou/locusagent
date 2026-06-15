"""Host workspace bootstrap from on-disk agent data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agentpod_host.db.models import Base, Workspace
from agentpod_host.workspaces import (
    agent_sqlite_session_count,
    ensure_default_workspace,
    sync_workspaces_from_disk,
    workspace_dirs_on_disk,
)
from agentpod_shared.workspace_ids import generate_workspace_id, is_valid_workspace_id

WS_A = "ws_0123456789abcdef0123"
WS_B = "ws_0123456789abcdef0124"


@pytest.fixture
async def host_session(tmp_path, monkeypatch):
    home = tmp_path / "agentpod-home"
    (home / "workspaces").mkdir(parents=True)
    monkeypatch.setenv("AGENTPOD_HOME", str(home))

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'host.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, home
    await engine.dispose()


def _seed_agent_db(workspace_root: Path, workspace_id: str, session_titles: list[str]) -> None:
    ws_dir = workspace_root / workspace_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    db_path = ws_dir / "agent.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "id TEXT PRIMARY KEY, title TEXT, hidden INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        for idx, title in enumerate(session_titles):
            conn.execute(
                "INSERT INTO sessions (id, title) VALUES (?, ?)",
                (f"sess_{idx}", title),
            )


def test_generate_workspace_id_format():
    wid = generate_workspace_id()
    assert is_valid_workspace_id(wid)


@pytest.mark.asyncio
async def test_workspace_dirs_on_disk_skips_invalid_ids(host_session):
    _, home = host_session
    _seed_agent_db(home / "workspaces", WS_A, ["历史对话"])
    invalid = home / "workspaces" / "ws_default"
    invalid.mkdir()
    (invalid / "agent.sqlite").write_bytes(b"")
    assert workspace_dirs_on_disk() == [WS_A]


@pytest.mark.asyncio
async def test_sync_registers_disk_workspace(host_session):
    session, home = host_session
    _seed_agent_db(home / "workspaces", WS_A, ["历史对话"])
    await sync_workspaces_from_disk(session)
    row = (await session.execute(select(Workspace).where(Workspace.id == WS_A))).scalar_one()
    assert row.name.startswith("工作区")


@pytest.mark.asyncio
async def test_new_default_prefers_workspace_with_more_sessions(host_session):
    session, home = host_session
    _seed_agent_db(home / "workspaces", WS_A, ["a"])
    _seed_agent_db(home / "workspaces", WS_B, ["a", "b", "c"])

    default = await ensure_default_workspace(session)
    assert default.id == WS_B
    assert agent_sqlite_session_count(WS_B) == 3
