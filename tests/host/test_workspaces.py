"""Host workspace bootstrap from on-disk agent data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agentpod_host.db.models import Base, McpOauthCredential, Workspace
from agentpod_host.workspaces import (
    agent_sqlite_session_count,
    copy_mcp_oauth_credentials,
    copy_workspace_on_disk,
    delete_workspace_on_disk,
    ensure_default_workspace,
    suggest_workspace_copy_name,
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
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memory ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL)"
        )
        for idx, title in enumerate(session_titles):
            conn.execute(
                "INSERT INTO sessions (id, title) VALUES (?, ?)",
                (f"sess_{idx}", title),
            )
        conn.execute("INSERT INTO memory (content) VALUES (?)", ("remember this",))


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


def test_suggest_workspace_copy_name_truncates():
    assert suggest_workspace_copy_name("短名") == "短名 副本"
    long_name = "a" * 30
    copied = suggest_workspace_copy_name(long_name)
    assert len(copied) <= 25
    assert copied.endswith(" 副本")


@pytest.mark.asyncio
async def test_copy_workspace_on_disk_keeps_memory_not_sessions(host_session):
    _, home = host_session
    target = "ws_0123456789abcdef0125"
    _seed_agent_db(home / "workspaces", WS_A, ["chat one", "chat two"])
    (home / "workspaces" / WS_A / "mcp.yaml").write_text("servers: []\n", encoding="utf-8")

    copy_workspace_on_disk(WS_A, target)

    src_db = home / "workspaces" / WS_A / "agent.sqlite"
    dst_db = home / "workspaces" / target / "agent.sqlite"
    assert dst_db.is_file()
    assert (home / "workspaces" / target / "mcp.yaml").read_text(encoding="utf-8") == "servers: []\n"
    with sqlite3.connect(src_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2
    with sqlite3.connect(dst_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert conn.execute("SELECT content FROM memory").fetchone()[0] == "remember this"


@pytest.mark.asyncio
async def test_copy_mcp_oauth_credentials(host_session):
    session, home = host_session
    _seed_agent_db(home / "workspaces", WS_A, [])
    _seed_agent_db(home / "workspaces", WS_B, [])
    session.add(
        Workspace(id=WS_A, name="源", description="", is_default=True),
    )
    session.add(
        Workspace(id=WS_B, name="目标", description="", is_default=False),
    )
    session.add(
        McpOauthCredential(
            workspace_id=WS_A,
            server_name="notion",
            server_url="https://example.com/mcp",
            tokens_enc=b"enc",
            client_info_enc=b"client",
        )
    )
    await session.flush()

    await copy_mcp_oauth_credentials(session, source_id=WS_A, target_id=WS_B)
    row = (
        await session.execute(
            select(McpOauthCredential).where(McpOauthCredential.workspace_id == WS_B)
        )
    ).scalar_one()
    assert row.server_name == "notion"
    assert row.tokens_enc == b"enc"


@pytest.mark.asyncio
async def test_delete_workspace_removes_mcp_oauth_credentials(host_session):
    session, home = host_session
    target = "ws_0123456789abcdef0125"
    _seed_agent_db(home / "workspaces", WS_A, [])
    _seed_agent_db(home / "workspaces", target, [])
    session.add(Workspace(id=WS_A, name="源", description="", is_default=True))
    session.add(Workspace(id=target, name="副本", description="", is_default=False))
    session.add(
        McpOauthCredential(
            workspace_id=WS_A,
            server_name="notion",
            server_url="https://example.com/mcp",
            tokens_enc=b"enc",
            client_info_enc=b"client",
        )
    )
    await session.flush()
    await copy_mcp_oauth_credentials(session, source_id=WS_A, target_id=target)

    row = (await session.execute(select(Workspace).where(Workspace.id == target))).scalar_one()
    await session.delete(row)
    await session.flush()

    remaining = (
        await session.execute(select(McpOauthCredential).where(McpOauthCredential.workspace_id == target))
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_delete_workspace_on_disk(host_session):
    _, home = host_session
    _seed_agent_db(home / "workspaces", WS_A, ["chat"])
    path = home / "workspaces" / WS_A
    assert path.is_dir()

    delete_workspace_on_disk(WS_A)

    assert not path.exists()
