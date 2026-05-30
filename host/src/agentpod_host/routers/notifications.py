"""用户站内通知 API（session 鉴权）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from ..auth import AuthContext, require_session
from ..auth.dependencies import _load_user_by_id
from ..auth.session import parse_session_user_id, SESSION_COOKIE_NAME
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

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
log = get_logger("notifications")


class NotificationCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    kind: str = Field(default="info")
    category: str | None = Field(default=None, max_length=64)
    link: str | None = Field(default=None, max_length=500)


@router.get("")
async def get_notifications(
    ctx: AuthContext = Depends(require_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    items = await list_notifications(ctx.user.id, limit=limit, unread_only=True)
    count = await unread_count(ctx.user.id)
    return {"items": items, "unread_count": count}


@router.get("/unread-count")
async def get_unread_count(ctx: AuthContext = Depends(require_session)) -> dict:
    return {"count": await unread_count(ctx.user.id)}


@router.post("")
async def post_notification(
    payload: NotificationCreateIn,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    try:
        item = await create_notification(
            ctx.user.id,
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
    notification_id: int,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    ok = await mark_read(ctx.user.id, notification_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="notification not found")
    return {"ok": True}


@router.post("/read-all")
async def read_all(ctx: AuthContext = Depends(require_session)) -> dict:
    updated = await mark_all_read(ctx.user.id)
    return {"updated": updated}


@router.delete("/{notification_id}")
async def remove_one(
    notification_id: int,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    ok = await delete_notification(ctx.user.id, notification_id)
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

    await hub.connect(user.id, websocket)
    try:
        items = await list_notifications(user.id, limit=50, unread_only=True)
        count = await unread_count(user.id)
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
        await hub.disconnect(user.id, websocket)
