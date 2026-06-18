"""MCP OAuth：外部浏览器授权 → Host 存 token → Agent 经 internal API 取用。"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ..agent_fetch import fetch_mcp_server_config, notify_agent_mcp_disconnect, notify_agent_mcp_reconnect
from ..auth import AuthContext, require_session
from ..auth.session import issue_mcp_oauth_state, verify_mcp_oauth_state
from ..db import get_session
from ..logging import get_logger
from ..mcp_oauth import store
from ..mcp_oauth.service import (
    McpOAuthError,
    PendingOAuthFlow,
    build_authorization_url,
    clear_pending,
    exchange_authorization_code,
    load_pending,
    store_pending,
)
from ..oauth_external import oauth_callback_html
from ..app_cache import get_app_cache
from ..workspaces import requested_workspace_id, resolve_workspace

router = APIRouter(prefix="/api/oauth/mcp", tags=["oauth-mcp"])
log = get_logger("oauth_mcp")


async def _begin_oauth_flow(
    *,
    wid: str,
    server: str,
) -> tuple[str, PendingOAuthFlow]:
    async with get_session() as session:
        await resolve_workspace(session, workspace_id=wid)

    cfg = await fetch_mcp_server_config(wid, server)
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
            workspace_id=wid,
            server_name=server,
            server_url=server_url,
        )
    except McpOAuthError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    cache = get_app_cache()
    await store_pending(pending, cache)
    apod_state = issue_mcp_oauth_state(workspace_id=wid, server_name=server)
    await cache.set(
        f"mcp_oauth_apod_state:{pending.oauth_state}",
        apod_state,
        ex=600,
    )
    log.info("mcp_oauth_start", workspace_id=wid, server=server)
    return authorize_url, pending


@router.get("/authorize-url")
async def mcp_oauth_authorize_url(
    request: Request,
    server: str = Query(..., min_length=1, max_length=128),
    workspace_id: str = Query(default=""),
    ctx: AuthContext = Depends(require_session),
) -> dict:
    """返回 OAuth 授权 URL，由客户端用系统浏览器打开。"""
    _ = ctx
    wid = (workspace_id or requested_workspace_id(request) or "").strip()
    if not wid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="workspace_id required")

    authorize_url, _pending = await _begin_oauth_flow(wid=wid, server=server)
    return {"authorize_url": authorize_url}


@router.get("/start")
async def mcp_oauth_start(
    request: Request,
    server: str = Query(..., min_length=1, max_length=128),
    workspace_id: str = Query(default=""),
    ctx: AuthContext = Depends(require_session),
) -> RedirectResponse:
    """兼容旧链：仍重定向到授权页（不推荐在应用内 webview 使用）。"""
    _ = ctx
    wid = (workspace_id or requested_workspace_id(request) or "").strip()
    if not wid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="workspace_id required")

    authorize_url, _pending = await _begin_oauth_flow(wid=wid, server=server)
    return RedirectResponse(authorize_url)


@router.get("/callback")
async def mcp_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> HTMLResponse:
    if error:
        log.warning("mcp_oauth_provider_error", error=error)
        return HTMLResponse(
            oauth_callback_html(ok=False, message=error),
            status_code=200,
        )

    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="missing code or state")

    cache = get_app_cache()
    pending = await load_pending(state, cache)
    if pending is None:
        return HTMLResponse(
            oauth_callback_html(ok=False, message="授权状态无效或已过期"),
            status_code=400,
        )

    apod_state_raw = await cache.get(f"mcp_oauth_apod_state:{state}")
    apod_ctx = verify_mcp_oauth_state(apod_state_raw or "")
    if apod_ctx is None:
        return HTMLResponse(
            oauth_callback_html(ok=False, message="授权上下文无效"),
            status_code=400,
        )
    if (
        apod_ctx["workspace_id"] != pending.workspace_id
        or apod_ctx["server_name"] != pending.server_name
    ):
        return HTMLResponse(
            oauth_callback_html(ok=False, message="授权上下文不匹配"),
            status_code=400,
        )

    try:
        await exchange_authorization_code(pending=pending, code=code)
    except Exception as exc:
        log.error(
            "mcp_oauth_exchange_failed",
            workspace_id=pending.workspace_id,
            server=pending.server_name,
            error=str(exc),
        )
        await clear_pending(state, cache)
        await cache.delete(f"mcp_oauth_apod_state:{state}")
        return HTMLResponse(
            oauth_callback_html(ok=False, message=str(exc)),
            status_code=502,
        )

    await clear_pending(state, cache)
    await cache.delete(f"mcp_oauth_apod_state:{state}")
    log.info(
        "mcp_oauth_callback_ok",
        workspace_id=pending.workspace_id,
        server=pending.server_name,
    )
    await notify_agent_mcp_reconnect(
        pending.workspace_id,
        pending.server_name,
    )
    return HTMLResponse(
        oauth_callback_html(ok=True, server_name=pending.server_name),
        status_code=200,
    )


@router.delete("/{server_name}")
async def mcp_oauth_disconnect(
    server_name: str,
    request: Request,
    workspace_id: str = Query(default=""),
    ctx: AuthContext = Depends(require_session),
) -> dict:
    _ = ctx
    wid = (workspace_id or requested_workspace_id(request) or "").strip()
    if not wid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="workspace_id required")
    async with get_session() as session:
        await resolve_workspace(session, workspace_id=wid)
    deleted = await store.delete_credential(
        workspace_id=wid,
        server_name=server_name,
    )
    if deleted:
        await notify_agent_mcp_disconnect(wid, server_name)
    return {"deleted": deleted}
