"""Agent → Host internal API: MCP OAuth 凭据。"""

from __future__ import annotations

from typing import Any

import httpx

from .host_internal import HostInternalError, error_detail, internal_base_and_headers
from .logging import get_logger

log = get_logger("host_mcp_oauth")


class HostMcpOAuthError(RuntimeError):
    pass


async def _request(method: str, path: str, *, workspace_id: str, json_body: dict | None = None) -> dict:
    base, headers = internal_base_and_headers(workspace_id=workspace_id)
    url = f"{base}{path}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        resp = await client.request(method, url, headers=headers, json=json_body)
    if resp.status_code >= 400:
        raise HostMcpOAuthError(error_detail(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def fetch_oauth_status(workspace_id: str) -> set[str]:
    try:
        data = await _request("GET", "/internal/mcp-oauth/status", workspace_id=workspace_id)
    except (HostInternalError, HostMcpOAuthError) as exc:
        log.warning("mcp_oauth_status_failed", workspace_id=workspace_id, error=str(exc))
        return set()
    servers = data.get("connected_servers")
    if not isinstance(servers, list):
        return set()
    return {str(s) for s in servers if isinstance(s, str)}


async def fetch_credentials(server_name: str, *, workspace_id: str) -> dict[str, Any]:
    path = f"/internal/mcp-oauth/credentials/{server_name}"
    return await _request("GET", path, workspace_id=workspace_id)


async def update_tokens(server_name: str, *, workspace_id: str, tokens: dict) -> None:
    path = f"/internal/mcp-oauth/credentials/{server_name}/tokens"
    await _request("PUT", path, workspace_id=workspace_id, json_body={"tokens": tokens})
