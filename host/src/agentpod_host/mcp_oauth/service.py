"""MCP OAuth 授权流程（RFC 9728 / OAuth 2.1 + PKCE）。"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from mcp.client.auth import OAuthTokenError
from mcp.client.auth.oauth2 import PKCEParameters
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_client_registration_request,
    create_oauth_metadata_request,
    extract_resource_metadata_from_www_auth,
    extract_scope_from_www_auth,
    get_client_metadata_scopes,
    handle_auth_metadata_response,
    handle_protected_resource_response,
    handle_registration_response,
    handle_token_response_scopes,
)
from mcp.client.streamable_http import MCP_PROTOCOL_VERSION
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthMetadata,
    OAuthToken,
)
from mcp.shared.auth_utils import resource_url_from_server_url
from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import AnyUrl

from ..config import get_settings
from ..logging import get_logger
from . import store

log = get_logger("mcp_oauth")

PENDING_TTL_SECONDS = 600
PENDING_KEY_PREFIX = "mcp_oauth_pending:"


@dataclass(slots=True)
class PendingOAuthFlow:
    user_id: int
    workspace_id: str
    server_name: str
    server_url: str
    code_verifier: str
    oauth_state: str
    client_info: dict


class McpOAuthError(RuntimeError):
    pass


def _client_metadata(redirect_uri: str) -> OAuthClientMetadata:
    return OAuthClientMetadata(
        client_name="AgentPod",
        redirect_uris=[AnyUrl(redirect_uri)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )


def _auth_base_url(server_url: str) -> str:
    parsed = urlparse(server_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _resource_param(server_url: str, prm_resource: str | None) -> str:
    if prm_resource:
        return prm_resource
    return resource_url_from_server_url(server_url)


async def _probe_www_auth(server_url: str) -> tuple[str | None, str | None]:
    headers = {MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=False) as client:
        for method in ("POST", "GET"):
            try:
                resp = await client.request(method, server_url, headers=headers, json={} if method == "POST" else None)
            except httpx.HTTPError:
                continue
            if resp.status_code == 401:
                return (
                    extract_resource_metadata_from_www_auth(resp),
                    extract_scope_from_www_auth(resp),
                )
    return None, None


async def _discover_prm(server_url: str, www_auth_url: str | None) -> tuple[object, str | None]:
    urls = build_protected_resource_metadata_discovery_urls(www_auth_url, server_url)
    headers = {MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        for url in urls:
            resp = await client.get(url, headers=headers)
            prm = await handle_protected_resource_response(resp)
            if prm is not None:
                auth_server = str(prm.authorization_servers[0]) if prm.authorization_servers else None
                return prm, auth_server
    raise McpOAuthError("无法发现 MCP OAuth 受保护资源元数据")


async def _discover_oauth_metadata(auth_server_url: str | None, server_url: str) -> OAuthMetadata | None:
    urls = build_oauth_authorization_server_metadata_discovery_urls(auth_server_url, server_url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        for url in urls:
            req = create_oauth_metadata_request(url)
            resp = await client.get(req.url, headers=dict(req.headers))
            ok, metadata = await handle_auth_metadata_response(resp)
            if not ok:
                break
            if metadata is not None:
                return metadata
    return None


async def _register_client(
    *,
    server_url: str,
    oauth_metadata: OAuthMetadata | None,
    redirect_uri: str,
) -> OAuthClientInformationFull:
    metadata = _client_metadata(redirect_uri)
    req = create_client_registration_request(oauth_metadata, metadata, _auth_base_url(server_url))
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        resp = await client.post(req.url, json=json.loads(req.content.decode()), headers=dict(req.headers))
    return await handle_registration_response(resp)


async def _ensure_client_info(
    *,
    user_id: int,
    workspace_id: str,
    server_name: str,
    server_url: str,
    oauth_metadata: OAuthMetadata | None,
    redirect_uri: str,
) -> OAuthClientInformationFull:
    existing = await store.load_client_info(
        user_id=user_id,
        workspace_id=workspace_id,
        server_name=server_name,
    )
    if existing is not None and existing.client_id:
        return existing
    client_info = await _register_client(
        server_url=server_url,
        oauth_metadata=oauth_metadata,
        redirect_uri=redirect_uri,
    )
    await store.save_client_info(
        user_id=user_id,
        workspace_id=workspace_id,
        server_name=server_name,
        server_url=server_url,
        client_info=client_info,
    )
    return client_info


async def build_authorization_url(
    *,
    user_id: int,
    workspace_id: str,
    server_name: str,
    server_url: str,
) -> tuple[str, PendingOAuthFlow]:
    settings = get_settings()
    redirect_uri = settings.mcp_oauth_redirect_uri
    www_auth_url, www_scope = await _probe_www_auth(server_url)
    prm, auth_server_url = await _discover_prm(server_url, www_auth_url)
    oauth_metadata = await _discover_oauth_metadata(auth_server_url, server_url)
    client_info = await _ensure_client_info(
        user_id=user_id,
        workspace_id=workspace_id,
        server_name=server_name,
        server_url=server_url,
        oauth_metadata=oauth_metadata,
        redirect_uri=redirect_uri,
    )
    scope = get_client_metadata_scopes(www_scope, prm, oauth_metadata)
    pkce = PKCEParameters.generate()
    oauth_state = secrets.token_urlsafe(32)

    if oauth_metadata and oauth_metadata.authorization_endpoint:
        auth_endpoint = str(oauth_metadata.authorization_endpoint)
    else:
        auth_endpoint = urljoin(_auth_base_url(server_url), "/authorize")

    prm_resource = str(prm.resource) if getattr(prm, "resource", None) else None
    auth_params = {
        "response_type": "code",
        "client_id": client_info.client_id,
        "redirect_uri": redirect_uri,
        "state": oauth_state,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": "S256",
        "resource": _resource_param(server_url, prm_resource),
    }
    if scope:
        auth_params["scope"] = scope

    pending = PendingOAuthFlow(
        user_id=user_id,
        workspace_id=workspace_id,
        server_name=server_name,
        server_url=server_url,
        code_verifier=pkce.code_verifier,
        oauth_state=oauth_state,
        client_info=store.client_info_to_dict(client_info),
    )
    return f"{auth_endpoint}?{urlencode(auth_params)}", pending


def pending_redis_key(oauth_state: str) -> str:
    return f"{PENDING_KEY_PREFIX}{oauth_state}"


async def store_pending(flow: PendingOAuthFlow, redis) -> None:
    payload = {
        "user_id": flow.user_id,
        "workspace_id": flow.workspace_id,
        "server_name": flow.server_name,
        "server_url": flow.server_url,
        "code_verifier": flow.code_verifier,
        "oauth_state": flow.oauth_state,
        "client_info": flow.client_info,
    }
    await redis.set(pending_redis_key(flow.oauth_state), json.dumps(payload), ex=PENDING_TTL_SECONDS)


async def load_pending(oauth_state: str, redis) -> PendingOAuthFlow | None:
    raw = await redis.get(pending_redis_key(oauth_state))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return PendingOAuthFlow(
            user_id=int(data["user_id"]),
            workspace_id=str(data["workspace_id"]),
            server_name=str(data["server_name"]),
            server_url=str(data["server_url"]),
            code_verifier=str(data["code_verifier"]),
            oauth_state=str(data["oauth_state"]),
            client_info=data["client_info"],
        )
    except (KeyError, TypeError, ValueError):
        return None


async def clear_pending(oauth_state: str, redis) -> None:
    await redis.delete(pending_redis_key(oauth_state))


async def exchange_authorization_code(
    *,
    pending: PendingOAuthFlow,
    code: str,
) -> OAuthToken:
    settings = get_settings()
    redirect_uri = settings.mcp_oauth_redirect_uri
    client_info = store.client_info_from_dict(pending.client_info)
    www_auth_url, www_scope = await _probe_www_auth(pending.server_url)
    prm, auth_server_url = await _discover_prm(pending.server_url, www_auth_url)
    oauth_metadata = await _discover_oauth_metadata(auth_server_url, pending.server_url)

    if oauth_metadata and oauth_metadata.token_endpoint:
        token_url = str(oauth_metadata.token_endpoint)
    else:
        token_url = urljoin(_auth_base_url(pending.server_url), "/token")

    prm_resource = str(prm.resource) if getattr(prm, "resource", None) else None
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_info.client_id,
        "code_verifier": pending.code_verifier,
        "resource": _resource_param(pending.server_url, prm_resource),
    }
    if get_client_metadata_scopes(www_scope, prm, oauth_metadata):
        token_data["scope"] = get_client_metadata_scopes(www_scope, prm, oauth_metadata)

    headers = {"Content-Type": "application/x-www-form-urlencoded", MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        resp = await client.post(token_url, data=token_data, headers=headers)
    if resp.status_code != 200:
        body = resp.text.strip()
        raise OAuthTokenError(f"Token exchange failed ({resp.status_code}): {body}")
    tokens = await handle_token_response_scopes(resp)
    await store.save_tokens(
        user_id=pending.user_id,
        workspace_id=pending.workspace_id,
        server_name=pending.server_name,
        server_url=pending.server_url,
        client_info=client_info,
        tokens=tokens,
    )
    return tokens


async def refresh_oauth_tokens(
    *,
    user_id: int,
    workspace_id: str,
    server_name: str,
) -> OAuthToken:
    row = await store.get_credential(user_id=user_id, workspace_id=workspace_id, server_name=server_name)
    if row is None:
        raise McpOAuthError("credential not found")
    server_url = (row.server_url or "").strip()
    if not server_url:
        raise McpOAuthError("server url missing")

    tokens = await store.load_tokens(user_id=user_id, workspace_id=workspace_id, server_name=server_name)
    client_info = await store.load_client_info(user_id=user_id, workspace_id=workspace_id, server_name=server_name)
    if tokens is None or not tokens.refresh_token:
        raise McpOAuthError("no refresh token")
    if client_info is None or not client_info.client_id:
        raise McpOAuthError("no client info")

    www_auth_url, www_scope = await _probe_www_auth(server_url)
    prm, auth_server_url = await _discover_prm(server_url, www_auth_url)
    oauth_metadata = await _discover_oauth_metadata(auth_server_url, server_url)

    if oauth_metadata and oauth_metadata.token_endpoint:
        token_url = str(oauth_metadata.token_endpoint)
    else:
        token_url = urljoin(_auth_base_url(server_url), "/token")

    prm_resource = str(prm.resource) if getattr(prm, "resource", None) else None
    refresh_data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": tokens.refresh_token,
        "client_id": client_info.client_id,
        "resource": _resource_param(server_url, prm_resource),
    }
    scope = get_client_metadata_scopes(www_scope, prm, oauth_metadata)
    if scope:
        refresh_data["scope"] = scope

    headers = {"Content-Type": "application/x-www-form-urlencoded", MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        resp = await client.post(token_url, data=refresh_data, headers=headers)
    if resp.status_code != 200:
        body = resp.text.strip()
        raise OAuthTokenError(f"Token refresh failed ({resp.status_code}): {body}")
    new_tokens = await handle_token_response_scopes(resp)
    ok = await store.update_tokens(
        user_id=user_id,
        workspace_id=workspace_id,
        server_name=server_name,
        tokens=new_tokens,
    )
    if not ok:
        raise McpOAuthError("credential not found")
    return new_tokens
