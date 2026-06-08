"""MCP OAuth 凭据持久化（Host SQLite + Fernet）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from ..db import McpOauthCredential, get_session
from ..logging import get_logger
from ..security import decrypt_str, encrypt_str

log = get_logger("mcp_oauth_store")


def _encrypt_json(payload: dict) -> bytes:
    return encrypt_str(json.dumps(payload, separators=(",", ":")))


def _decrypt_json(token: bytes) -> dict:
    return json.loads(decrypt_str(token))


def _decrypt_json_safe(token: bytes) -> dict | None:
    try:
        return _decrypt_json(token)
    except RuntimeError as exc:
        log.warning("mcp_oauth_decrypt_failed", error=str(exc))
        return None


async def _delete_credential_row(row: McpOauthCredential) -> None:
    async with get_session() as session:
        db_row = await session.get(McpOauthCredential, row.id)
        if db_row is not None:
            await session.delete(db_row)


async def _drop_corrupt_credential(
    row: McpOauthCredential,
    *,
    workspace_id: str,
    server_name: str,
) -> None:
    log.warning(
        "mcp_oauth_credential_dropped",
        workspace_id=workspace_id,
        server=server_name,
        reason="decrypt_failed",
    )
    await _delete_credential_row(row)


def tokens_to_dict(tokens: OAuthToken) -> dict:
    return tokens.model_dump(mode="json", exclude_none=True)


def tokens_from_dict(data: dict) -> OAuthToken:
    return OAuthToken.model_validate(data)


def client_info_to_dict(info: OAuthClientInformationFull) -> dict:
    return info.model_dump(mode="json", exclude_none=True)


def client_info_from_dict(data: dict) -> OAuthClientInformationFull:
    return OAuthClientInformationFull.model_validate(data)


async def get_credential(
    *,
    workspace_id: str,
    server_name: str,
) -> McpOauthCredential | None:
    async with get_session() as session:
        stmt = select(McpOauthCredential).where(
            McpOauthCredential.workspace_id == workspace_id,
            McpOauthCredential.server_name == server_name,
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def list_oauth_connected_servers(*, workspace_id: str) -> set[str]:
    async with get_session() as session:
        stmt = select(McpOauthCredential).where(
            McpOauthCredential.workspace_id == workspace_id,
            McpOauthCredential.tokens_enc.is_not(None),
        )
        rows = (await session.execute(stmt)).scalars().all()
    connected: set[str] = set()
    for row in rows:
        if row.tokens_enc is None:
            continue
        if _decrypt_json_safe(row.tokens_enc) is None:
            await _drop_corrupt_credential(row, workspace_id=workspace_id, server_name=row.server_name)
            continue
        connected.add(row.server_name)
    return connected


async def load_tokens(
    *,
    workspace_id: str,
    server_name: str,
) -> OAuthToken | None:
    row = await get_credential(workspace_id=workspace_id, server_name=server_name)
    if row is None or row.tokens_enc is None:
        return None
    data = _decrypt_json_safe(row.tokens_enc)
    if data is None:
        await _drop_corrupt_credential(row, workspace_id=workspace_id, server_name=server_name)
        return None
    return tokens_from_dict(data)


async def load_client_info(
    *,
    workspace_id: str,
    server_name: str,
) -> OAuthClientInformationFull | None:
    row = await get_credential(workspace_id=workspace_id, server_name=server_name)
    if row is None:
        return None
    data = _decrypt_json_safe(row.client_info_enc)
    if data is None:
        await _drop_corrupt_credential(row, workspace_id=workspace_id, server_name=server_name)
        return None
    return client_info_from_dict(data)


async def save_client_info(
    *,
    workspace_id: str,
    server_name: str,
    server_url: str,
    client_info: OAuthClientInformationFull,
) -> None:
    payload = _encrypt_json(client_info_to_dict(client_info))
    now = datetime.now(UTC)
    async with get_session() as session:
        stmt = (
            insert(McpOauthCredential)
            .values(
                workspace_id=workspace_id,
                server_name=server_name,
                server_url=server_url,
                client_info_enc=payload,
                tokens_enc=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["workspace_id", "server_name"],
                set_={
                    "server_url": server_url,
                    "client_info_enc": payload,
                    "updated_at": now,
                },
            )
        )
        await session.execute(stmt)


async def save_tokens(
    *,
    workspace_id: str,
    server_name: str,
    server_url: str,
    client_info: OAuthClientInformationFull,
    tokens: OAuthToken,
) -> None:
    client_payload = _encrypt_json(client_info_to_dict(client_info))
    token_payload = _encrypt_json(tokens_to_dict(tokens))
    now = datetime.now(UTC)
    async with get_session() as session:
        stmt = (
            insert(McpOauthCredential)
            .values(
                workspace_id=workspace_id,
                server_name=server_name,
                server_url=server_url,
                client_info_enc=client_payload,
                tokens_enc=token_payload,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["workspace_id", "server_name"],
                set_={
                    "server_url": server_url,
                    "client_info_enc": client_payload,
                    "tokens_enc": token_payload,
                    "updated_at": now,
                },
            )
        )
        await session.execute(stmt)


async def update_tokens(
    *,
    workspace_id: str,
    server_name: str,
    tokens: OAuthToken,
) -> bool:
    row = await get_credential(workspace_id=workspace_id, server_name=server_name)
    if row is None:
        return False
    token_payload = _encrypt_json(tokens_to_dict(tokens))
    now = datetime.now(UTC)
    async with get_session() as session:
        db_row = await session.get(McpOauthCredential, row.id)
        if db_row is None:
            return False
        db_row.tokens_enc = token_payload
        db_row.updated_at = now
    return True


async def delete_credential(*, workspace_id: str, server_name: str) -> bool:
    row = await get_credential(workspace_id=workspace_id, server_name=server_name)
    if row is None:
        return False
    await _delete_credential_row(row)
    return True
