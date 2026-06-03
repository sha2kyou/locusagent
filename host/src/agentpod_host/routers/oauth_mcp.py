"""MCP OAuth：浏览器授权 → Host 存 token → Agent 经 internal API 取用。"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from ..agent_fetch import fetch_mcp_server_config, notify_agent_mcp_disconnect, notify_agent_mcp_reconnect
from ..auth import AuthContext, require_session
from ..auth.session import issue_mcp_oauth_state, verify_mcp_oauth_state
from ..db import get_session
from ..logging import get_logger
from ..mcp_oauth import store
from ..mcp_oauth.service import (
    McpOAuthError,
    build_authorization_url,
    clear_pending,
    exchange_authorization_code,
    load_pending,
    store_pending,
)
from ..redis_client import get_redis
from ..workspaces import requested_workspace_id, resolve_workspace

router = APIRouter(prefix="/api/oauth/mcp", tags=["oauth-mcp"])
log = get_logger("oauth_mcp")


def _mcp_page_url(*, workspace_id: str, server_name: str, oauth: str) -> str:
    params = urlencode({"oauth": oauth, "server": server_name})
    return f"/w/{workspace_id}/mcp?{params}"


@router.get("/start")
async def mcp_oauth_start(
    request: Request,
    server: str = Query(..., min_length=1, max_length=128),
    workspace_id: str = Query(default=""),
    ctx: AuthContext = Depends(require_session),
) -> RedirectResponse:
    wid = (workspace_id or requested_workspace_id(request) or "").strip()
    if not wid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="workspace_id required")

    async with get_session() as session:
        await resolve_workspace(session, user_id=ctx.user.id, workspace_id=wid)

    cfg = await fetch_mcp_server_config(ctx.user.id, wid, server)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="mcp server not found")
    if cfg.get("transport") != "http":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="oauth only supported for http transport")
    if cfg.get("auth") != "oauth":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="server does not support oauth")
    server_url = str(cfg.get("url") or "").strip()
    if not server_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="mcp server url missing")

    try:
        authorize_url, pending = await build_authorization_url(
            user_id=ctx.user.id,
            workspace_id=wid,
            server_name=server,
            server_url=server_url,
        )
    except McpOAuthError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    redis = get_redis()
    await store_pending(pending, redis)
    apod_state = issue_mcp_oauth_state(user_id=ctx.user.id, workspace_id=wid, server_name=server)
    await redis.set(
        f"mcp_oauth_apod_state:{pending.oauth_state}",
        apod_state,
        ex=600,
    )
    log.info("mcp_oauth_start", user_id=ctx.user.id, workspace_id=wid, server=server)
    return RedirectResponse(authorize_url)


@router.get("/callback")
async def mcp_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    fallback = "/mcp"

    if error:
        log.warning("mcp_oauth_provider_error", error=error)
        return RedirectResponse(f"{fallback}?oauth=error")

    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="missing code or state")

    redis = get_redis()
    pending = await load_pending(state, redis)
    if pending is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid or expired oauth state")

    apod_state_raw = await redis.get(f"mcp_oauth_apod_state:{state}")
    apod_ctx = verify_mcp_oauth_state(apod_state_raw or "")
    if apod_ctx is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid apod state")
    if (
        apod_ctx["user_id"] != pending.user_id
        or apod_ctx["workspace_id"] != pending.workspace_id
        or apod_ctx["server_name"] != pending.server_name
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="oauth context mismatch")

    try:
        await exchange_authorization_code(pending=pending, code=code)
    except Exception as exc:
        log.error(
            "mcp_oauth_exchange_failed",
            user_id=pending.user_id,
            workspace_id=pending.workspace_id,
            server=pending.server_name,
            error=str(exc),
        )
        await clear_pending(state, redis)
        await redis.delete(f"mcp_oauth_apod_state:{state}")
        return RedirectResponse(_mcp_page_url(
            workspace_id=pending.workspace_id,
            server_name=pending.server_name,
            oauth="error",
        ))

    await clear_pending(state, redis)
    await redis.delete(f"mcp_oauth_apod_state:{state}")
    log.info(
        "mcp_oauth_callback_ok",
        user_id=pending.user_id,
        workspace_id=pending.workspace_id,
        server=pending.server_name,
    )
    await notify_agent_mcp_reconnect(
        pending.user_id,
        pending.workspace_id,
        pending.server_name,
    )
    return RedirectResponse(_mcp_page_url(
        workspace_id=pending.workspace_id,
        server_name=pending.server_name,
        oauth="success",
    ))


@router.delete("/{server_name}")
async def mcp_oauth_disconnect(
    server_name: str,
    request: Request,
    workspace_id: str = Query(default=""),
    ctx: AuthContext = Depends(require_session),
) -> dict:
    wid = (workspace_id or requested_workspace_id(request) or "").strip()
    if not wid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="workspace_id required")
    async with get_session() as session:
        await resolve_workspace(session, user_id=ctx.user.id, workspace_id=wid)
    deleted = await store.delete_credential(
        user_id=ctx.user.id,
        workspace_id=wid,
        server_name=server_name,
    )
    if deleted:
        await notify_agent_mcp_disconnect(ctx.user.id, wid, server_name)
    return {"deleted": deleted}
