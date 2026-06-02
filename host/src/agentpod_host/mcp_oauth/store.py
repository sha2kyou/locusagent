"""MCP OAuth 凭据持久化（Host Postgres + Fernet）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..db import McpOauthCredential, get_session
from ..security import decrypt_str, encrypt_str


def _encrypt_json(payload: dict) -> bytes:
    return encrypt_str(json.dumps(payload, separators=(",", ":")))


def _decrypt_json(token: bytes) -> dict:
    return json.loads(decrypt_str(token))


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
    user_id: int,
    workspace_id: str,
    server_name: str,
) -> McpOauthCredential | None:
    async with get_session() as session:
        stmt = select(McpOauthCredential).where(
            McpOauthCredential.user_id == user_id,
            McpOauthCredential.workspace_id == workspace_id,
            McpOauthCredential.server_name == server_name,
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def list_oauth_connected_servers(*, user_id: int, workspace_id: str) -> set[str]:
    async with get_session() as session:
        stmt = select(McpOauthCredential.server_name).where(
            McpOauthCredential.user_id == user_id,
            McpOauthCredential.workspace_id == workspace_id,
            McpOauthCredential.tokens_enc.is_not(None),
        )
        rows = (await session.execute(stmt)).scalars().all()
        return set(rows)


async def load_tokens(
    *,
    user_id: int,
    workspace_id: str,
    server_name: str,
) -> OAuthToken | None:
    row = await get_credential(user_id=user_id, workspace_id=workspace_id, server_name=server_name)
    if row is None or row.tokens_enc is None:
        return None
    return tokens_from_dict(_decrypt_json(row.tokens_enc))


async def load_client_info(
    *,
    user_id: int,
    workspace_id: str,
    server_name: str,
) -> OAuthClientInformationFull | None:
    row = await get_credential(user_id=user_id, workspace_id=workspace_id, server_name=server_name)
    if row is None:
        return None
    return client_info_from_dict(_decrypt_json(row.client_info_enc))


async def save_client_info(
    *,
    user_id: int,
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
                user_id=user_id,
                workspace_id=workspace_id,
                server_name=server_name,
                server_url=server_url,
                client_info_enc=payload,
                tokens_enc=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "workspace_id", "server_name"],
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
    user_id: int,
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
                user_id=user_id,
                workspace_id=workspace_id,
                server_name=server_name,
                server_url=server_url,
                client_info_enc=client_payload,
                tokens_enc=token_payload,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "workspace_id", "server_name"],
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
    user_id: int,
    workspace_id: str,
    server_name: str,
    tokens: OAuthToken,
) -> bool:
    row = await get_credential(user_id=user_id, workspace_id=workspace_id, server_name=server_name)
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


async def delete_credential(*, user_id: int, workspace_id: str, server_name: str) -> bool:
    row = await get_credential(user_id=user_id, workspace_id=workspace_id, server_name=server_name)
    if row is None:
        return False
    async with get_session() as session:
        db_row = await session.get(McpOauthCredential, row.id)
        if db_row is not None:
            await session.delete(db_row)
    return True
