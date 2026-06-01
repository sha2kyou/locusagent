"""用户站内通知 API（session 鉴权）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from ..auth import AuthContext, require_session
from ..auth.dependencies import _load_user_by_id
from ..auth.session import parse_session_user_id, SESSION_COOKIE_NAME
from ..db import get_session
from ..logging import get_logger
from ..notifications import (
    create_notification,
    delete_notification,
    list_notifications,
    mark_all_read,
    mark_read,
    unread_count,
)
from ..notifications.hub import hub
from ..workspaces import requested_workspace_id, resolve_workspace

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
log = get_logger("notifications")


class NotificationCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    kind: str = Field(default="info")
    category: str | None = Field(default=None, max_length=64)
    link: str | None = Field(default=None, max_length=500)


async def _workspace_for_request(request: Request, user_id: int) -> str:
    async with get_session() as session:
        ws = await resolve_workspace(
            session,
            user_id=user_id,
            workspace_id=requested_workspace_id(request),
        )
    return ws.id


async def _workspace_for_ws(websocket: WebSocket, user_id: int) -> str:
    raw = websocket.headers.get("X-Workspace-Id") or websocket.query_params.get("workspace_id")
    workspace_id = (raw or "").strip().lower() or None
    async with get_session() as session:
        ws = await resolve_workspace(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    return ws.id


@router.get("")
async def get_notifications(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    workspace_id = await _workspace_for_request(request, ctx.user.id)
    items = await list_notifications(ctx.user.id, workspace_id=workspace_id, limit=limit, unread_only=True)
    count = await unread_count(ctx.user.id, workspace_id=workspace_id)
    return {"items": items, "unread_count": count}


@router.get("/unread-count")
async def get_unread_count(
    request: Request,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    workspace_id = await _workspace_for_request(request, ctx.user.id)
    return {"count": await unread_count(ctx.user.id, workspace_id=workspace_id)}


@router.post("")
async def post_notification(
    request: Request,
    payload: NotificationCreateIn,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    workspace_id = await _workspace_for_request(request, ctx.user.id)
    try:
        item = await create_notification(
            ctx.user.id,
            workspace_id=workspace_id,
            title=payload.title,
            body=payload.body,
            kind=payload.kind,
            category=payload.category,
            link=payload.link,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"item": item}


@router.post("/{notification_id}/read")
async def read_one(
    request: Request,
    notification_id: int,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    workspace_id = await _workspace_for_request(request, ctx.user.id)
    ok = await mark_read(ctx.user.id, notification_id, workspace_id=workspace_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="notification not found")
    return {"ok": True}


@router.post("/read-all")
async def read_all(
    request: Request,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    workspace_id = await _workspace_for_request(request, ctx.user.id)
    updated = await mark_all_read(ctx.user.id, workspace_id=workspace_id)
    return {"updated": updated}


@router.delete("/{notification_id}")
async def remove_one(
    request: Request,
    notification_id: int,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    workspace_id = await _workspace_for_request(request, ctx.user.id)
    ok = await delete_notification(ctx.user.id, notification_id, workspace_id=workspace_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="notification not found")
    return {"deleted": True}


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket) -> None:
    user_id = parse_session_user_id(websocket.cookies.get(SESSION_COOKIE_NAME))
    if user_id is None:
        await websocket.close(code=4401, reason="missing session")
        return
    user = await _load_user_by_id(user_id)
    if user is None:
        await websocket.close(code=4401, reason="invalid session")
        return

    workspace_id = await _workspace_for_ws(websocket, user.id)
    await hub.connect(user.id, workspace_id, websocket)
    try:
        items = await list_notifications(user.id, workspace_id=workspace_id, limit=50, unread_only=True)
        count = await unread_count(user.id, workspace_id=workspace_id)
        await websocket.send_json({"type": "sync", "items": items, "unread_count": count})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws_error", user_id=user.id, error=str(exc))
    finally:
        await hub.disconnect(user.id, workspace_id, websocket)
