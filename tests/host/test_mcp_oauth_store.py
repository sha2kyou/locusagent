"""MCP OAuth 凭据解密失败时的降级行为。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import asyncio

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from locus_host.config import get_settings
from locus_host.db import McpOauthCredential, Workspace, dispose_engine, get_session, init_engine
from locus_host.mcp_oauth import store
from locus_host.security.crypto import _fernet, encrypt_str


def _reset_engine_sync() -> None:
    asyncio.run(dispose_engine())
    get_settings.cache_clear()
    _fernet.cache_clear()


@pytest.fixture(autouse=True)
def _reset_host_db_engine():
    _reset_engine_sync()
    yield
    _reset_engine_sync()


WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture
async def oauth_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    key = Fernet.generate_key()
    db_path = tmp_path / "host.sqlite"
    monkeypatch.setenv("ENCRYPTION_KEY", key.decode("ascii"))
    monkeypatch.setenv("HOST_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()
    _fernet.cache_clear()
    await init_engine()
    async with get_session() as session:
        if await session.get(Workspace, WS_TEST) is None:
            session.add(Workspace(id=WS_TEST, name="test", is_default=True))
    yield


@pytest.mark.asyncio
async def test_load_tokens_drops_corrupt_credential(oauth_db) -> None:
    async with get_session() as session:
        session.add(
            McpOauthCredential(
                workspace_id=WS_TEST,
                server_name="notion",
                server_url="https://mcp.notion.com/mcp",
                client_info_enc=b"invalid-client-info",
                tokens_enc=b"invalid-tokens",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    tokens = await store.load_tokens(
        workspace_id=WS_TEST,
        server_name="notion",
    )
    assert tokens is None

    async with get_session() as session:
        row = (
            await session.execute(
                select(McpOauthCredential).where(
                    McpOauthCredential.workspace_id == WS_TEST,
                    McpOauthCredential.server_name == "notion",
                )
            )
        ).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_list_oauth_connected_skips_corrupt_rows(oauth_db) -> None:
    valid_payload = encrypt_str('{"access_token":"x","token_type":"Bearer"}')

    async with get_session() as session:
        session.add(
            McpOauthCredential(
                workspace_id=WS_TEST,
                server_name="good",
                server_url="https://example.com/mcp",
                client_info_enc=valid_payload,
                tokens_enc=valid_payload,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.add(
            McpOauthCredential(
                workspace_id=WS_TEST,
                server_name="bad",
                server_url="https://example.com/mcp",
                client_info_enc=b"bad",
                tokens_enc=b"bad",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    connected = await store.list_oauth_connected_servers(workspace_id=WS_TEST)
    assert connected == {"good"}

    async with get_session() as session:
        rows = (await session.execute(select(McpOauthCredential))).scalars().all()
    assert {row.server_name for row in rows} == {"good"}
