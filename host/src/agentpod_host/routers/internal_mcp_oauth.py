"""Agent 容器内部：MCP OAuth 凭据读写。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..db import User, get_session
from ..mcp_oauth import store
from ..mcp_oauth.service import McpOAuthError, refresh_oauth_tokens as do_refresh_oauth_tokens
from ..workspaces import requested_workspace_id, resolve_workspace

router = APIRouter(prefix="/internal/mcp-oauth", tags=["internal-mcp-oauth"])


class McpOAuthTokensIn(BaseModel):
    tokens: dict = Field(...)


async def _workspace_for_request(request: Request, user_id: int) -> str:
    async with get_session() as session:
        ws = await resolve_workspace(
            session,
            user_id=user_id,
            workspace_id=requested_workspace_id(request),
        )
        return ws.id


@router.get("/status")
async def mcp_oauth_status(
    request: Request,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    connected = await store.list_oauth_connected_servers(user_id=user.id, workspace_id=workspace_id)
    return {"connected_servers": sorted(connected)}


@router.get("/credentials/{server_name}")
async def mcp_oauth_get_credentials(
    server_name: str,
    request: Request,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    tokens = await store.load_tokens(
        user_id=user.id,
        workspace_id=workspace_id,
        server_name=server_name,
    )
    client_info = await store.load_client_info(
        user_id=user.id,
        workspace_id=workspace_id,
        server_name=server_name,
    )
    settings = get_settings()
    return {
        "connected": tokens is not None,
        "tokens": store.tokens_to_dict(tokens) if tokens else None,
        "client_info": store.client_info_to_dict(client_info) if client_info else None,
        "redirect_uri": settings.mcp_oauth_redirect_uri,
    }


@router.post("/credentials/{server_name}/refresh")
async def mcp_oauth_refresh_tokens(
    server_name: str,
    request: Request,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    try:
        tokens = await do_refresh_oauth_tokens(
            user_id=user.id,
            workspace_id=workspace_id,
            server_name=server_name,
        )
    except McpOAuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"refreshed": True, "tokens": store.tokens_to_dict(tokens)}


@router.put("/credentials/{server_name}/tokens")
async def mcp_oauth_update_tokens(
    server_name: str,
    payload: McpOAuthTokensIn,
    request: Request,
    user: User = Depends(require_agent_internal),
) -> dict:
    workspace_id = await _workspace_for_request(request, user.id)
    try:
        tokens = store.tokens_from_dict(payload.tokens)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid tokens") from exc
    ok = await store.update_tokens(
        user_id=user.id,
        workspace_id=workspace_id,
        server_name=server_name,
        tokens=tokens,
    )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="credential not found")
    return {"updated": True}
