"""探测远程 HTTP MCP 是否支持 OAuth DCR（registration_endpoint）。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_oauth_metadata_request,
    extract_resource_metadata_from_www_auth,
    handle_auth_metadata_response,
    handle_protected_resource_response,
)
from mcp.client.streamable_http import MCP_PROTOCOL_VERSION
from mcp.types import LATEST_PROTOCOL_VERSION

if TYPE_CHECKING:
    from .config import MCPServerConfig


class McpProbeError(RuntimeError):
    pass


_PROBE_HTTP_TIMEOUT = httpx.Timeout(8.0)
_PROBE_TOTAL_SECONDS = 15.0


async def _probe_www_auth(server_url: str) -> str | None:
    headers = {MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
    async with httpx.AsyncClient(timeout=_PROBE_HTTP_TIMEOUT, follow_redirects=False) as client:
        for method in ("POST", "GET"):
            try:
                resp = await client.request(
                    method,
                    server_url,
                    headers=headers,
                    json={} if method == "POST" else None,
                )
            except httpx.HTTPError:
                continue
            if resp.status_code == 401:
                return extract_resource_metadata_from_www_auth(resp)
    return None


async def _probe_http_oauth_supported(server_url: str) -> bool:
    """有 registration_endpoint 时返回 True，否则 False。"""
    url = server_url.strip()
    if not url:
        raise McpProbeError("url is required")

    www_auth_url = await _probe_www_auth(url)
    prm_urls = build_protected_resource_metadata_discovery_urls(www_auth_url, url)
    headers = {MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
    auth_server_url: str | None = None

    async with httpx.AsyncClient(timeout=_PROBE_HTTP_TIMEOUT) as client:
        for prm_url in prm_urls:
            try:
                resp = await client.get(prm_url, headers=headers)
            except httpx.HTTPError:
                continue
            prm = await handle_protected_resource_response(resp)
            if prm is not None:
                auth_server_url = str(prm.authorization_servers[0]) if prm.authorization_servers else None
                break

        meta_urls = build_oauth_authorization_server_metadata_discovery_urls(auth_server_url, url)
        for meta_url in meta_urls:
            req = create_oauth_metadata_request(meta_url)
            try:
                resp = await client.get(req.url, headers=dict(req.headers))
            except httpx.HTTPError:
                continue
            ok, metadata = await handle_auth_metadata_response(resp)
            if not ok:
                break
            if metadata is not None and metadata.registration_endpoint:
                return True
    return False


async def probe_http_oauth_supported(server_url: str) -> bool:
    try:
        return await asyncio.wait_for(_probe_http_oauth_supported(server_url), timeout=_PROBE_TOTAL_SECONDS)
    except TimeoutError:
        return False


async def build_http_mcp_config(
    *,
    name: str,
    url: str,
    headers: dict[str, str] | None = None,
    existing: MCPServerConfig | None = None,
) -> MCPServerConfig:
    """构建 HTTP MCP 配置：URL 未变时保留原 auth；变更时重新探测 OAuth。"""
    from .config import MCPServerConfig

    normalized_url = url.strip()
    if not normalized_url:
        raise McpProbeError("url is required")

    incoming_headers = dict(headers or {})
    existing_url = (existing.url or "").strip() if existing else ""
    url_unchanged = (
        existing is not None
        and existing.transport == "http"
        and existing_url == normalized_url
    )

    auth: str
    if url_unchanged:
        auth = existing.auth
    else:
        oauth_supported = await probe_http_oauth_supported(normalized_url)
        auth = "oauth" if oauth_supported else "none"

    if auth == "oauth":
        resolved_headers: dict[str, str] = {}
    elif url_unchanged and existing and not incoming_headers:
        resolved_headers = dict(existing.headers)
    else:
        resolved_headers = incoming_headers

    return MCPServerConfig(
        name=name,
        transport="http",
        url=normalized_url,
        headers=resolved_headers,
        auth=auth,
    )
