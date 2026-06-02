"""MCP HTTP OAuth：凭据存 Host，Agent 用 OAuthClientProvider 连接。"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.oauth2 import TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from pydantic import AnyUrl

from ..host_mcp_oauth import HostMcpOAuthError, fetch_credentials, update_tokens
from ..logging import get_logger

log = get_logger("mcp_oauth")

OAUTH_REQUIRED = "oauth_required"


class OAuthRequiredError(RuntimeError):
    pass


class HostBackedTokenStorage(TokenStorage):
    def __init__(self, *, server_name: str, workspace_id: str, redirect_uri: str) -> None:
        self._server_name = server_name
        self._workspace_id = workspace_id
        self._redirect_uri = redirect_uri
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None
        self._loaded = False

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

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        await self._ensure_loaded()
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


def _client_metadata(redirect_uri: str) -> OAuthClientMetadata:
    return OAuthClientMetadata(
        client_name="AgentPod",
        redirect_uris=[AnyUrl(redirect_uri)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )


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

    redirect_uri = storage._redirect_uri  # noqa: SLF001
    oauth_auth = OAuthClientProvider(
        server_url=server_url,
        client_metadata=_client_metadata(redirect_uri),
        storage=storage,
        redirect_handler=None,
        callback_handler=None,
    )
    transport = await stack.enter_async_context(
        streamablehttp_client(server_url, auth=oauth_auth)
    )
    read, write, _ = transport
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session


async def probe_http_oauth(
    *,
    server_name: str,
    server_url: str,
    workspace_id: str,
) -> dict[str, Any]:
    stack = AsyncExitStack()
    try:
        session = await connect_http_oauth_session(
            stack,
            server_name=server_name,
            server_url=server_url,
            workspace_id=workspace_id,
        )
        listed = await session.list_tools()
        return {"connected": True, "tool_count": len(listed.tools)}
    except OAuthRequiredError:
        return {"connected": False, "error": OAUTH_REQUIRED}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}
    finally:
        await stack.aclose()
