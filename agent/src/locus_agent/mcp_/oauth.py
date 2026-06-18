"""MCP HTTP OAuth：凭据存 Host，Agent 用 Bearer + Host 刷新连接。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from ..host_mcp_oauth import HostMcpOAuthError, fetch_credentials, refresh_oauth_tokens, update_tokens
from ..logging import get_logger

log = get_logger("mcp_oauth")

OAUTH_REQUIRED = "oauth_required"

_oauth_connect_locks: dict[tuple[str, str], asyncio.Lock] = {}


class OAuthRequiredError(RuntimeError):
    pass


class HostBackedTokenStorage:
    """从 Host internal API 读写 token；浏览器授权只在 Host 完成。"""

    def __init__(self, *, server_name: str, workspace_id: str, redirect_uri: str) -> None:
        self._server_name = server_name
        self._workspace_id = workspace_id
        self._redirect_uri = redirect_uri
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None
        self._loaded = False

    def invalidate_cache(self) -> None:
        self._loaded = False
        self._tokens = None
        self._client_info = None

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        data = await fetch_credentials(self._server_name, workspace_id=self._workspace_id)
        tokens_raw = data.get("tokens")
        client_raw = data.get("client_info")
        if isinstance(tokens_raw, dict):
            self._tokens = OAuthToken.model_validate(tokens_raw)
        if isinstance(client_raw, dict):
            self._client_info = OAuthClientInformationFull.model_validate(client_raw)
        redirect = data.get("redirect_uri")
        if isinstance(redirect, str) and redirect.strip():
            self._redirect_uri = redirect.strip()
        self._loaded = True

    async def get_tokens(self) -> OAuthToken | None:
        await self._ensure_loaded()
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens
        payload = tokens.model_dump(mode="json", exclude_none=True)
        try:
            await update_tokens(self._server_name, workspace_id=self._workspace_id, tokens=payload)
        except HostMcpOAuthError as exc:
            log.warning(
                "mcp_oauth_token_persist_failed",
                server=self._server_name,
                workspace_id=self._workspace_id,
                error=str(exc),
            )


class HostOAuthBearerAuth(httpx.Auth):
    """仅用 Host 已存 token；401 时经 Host 刷新，不触发浏览器 OAuth。"""

    requires_response_body = True

    def __init__(
        self,
        *,
        storage: HostBackedTokenStorage,
        server_name: str,
        workspace_id: str,
    ) -> None:
        self._storage = storage
        self._server_name = server_name
        self._workspace_id = workspace_id
        self._refreshed = False

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        tokens = await self._storage.get_tokens()
        if not tokens or not tokens.access_token:
            raise OAuthRequiredError(OAUTH_REQUIRED)
        request.headers["Authorization"] = f"Bearer {tokens.access_token}"
        response = yield request
        if response.status_code not in (401, 403) or self._refreshed:
            return
        self._refreshed = True
        try:
            await refresh_oauth_tokens(self._server_name, workspace_id=self._workspace_id)
            self._storage.invalidate_cache()
        except HostMcpOAuthError as exc:
            log.warning(
                "mcp_oauth_refresh_failed",
                server=self._server_name,
                workspace_id=self._workspace_id,
                error=str(exc),
            )
            raise OAuthRequiredError(OAUTH_REQUIRED) from exc
        tokens = await self._storage.get_tokens()
        if not tokens or not tokens.access_token:
            raise OAuthRequiredError(OAUTH_REQUIRED)
        request.headers["Authorization"] = f"Bearer {tokens.access_token}"
        yield request


def oauth_connect_lock(workspace_id: str, server_name: str) -> asyncio.Lock:
    key = (workspace_id, server_name)
    lock = _oauth_connect_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _oauth_connect_locks[key] = lock
    return lock


async def connect_http_oauth_session(
    stack: AsyncExitStack,
    *,
    server_name: str,
    server_url: str,
    workspace_id: str,
) -> ClientSession:
    storage = HostBackedTokenStorage(
        server_name=server_name,
        workspace_id=workspace_id,
        redirect_uri="http://localhost/api/oauth/mcp/callback",
    )
    tokens = await storage.get_tokens()
    if tokens is None or not tokens.access_token:
        raise OAuthRequiredError(OAUTH_REQUIRED)

    auth = HostOAuthBearerAuth(storage=storage, server_name=server_name, workspace_id=workspace_id)
    async with oauth_connect_lock(workspace_id, server_name):
        transport = await stack.enter_async_context(streamablehttp_client(server_url, auth=auth))
        read, write, _ = transport
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
    return session
