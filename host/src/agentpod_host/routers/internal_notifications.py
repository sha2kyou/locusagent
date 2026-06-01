"""Agent 容器内部回调：写入用户站内通知。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..auth.agent_internal import require_agent_internal
from ..db import User, get_session
from ..notifications import create_notification, list_notifications, unread_count
from ..workspaces import resolve_workspace

router = APIRouter(prefix="/internal/notifications", tags=["internal-notifications"])


class AgentNotificationIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    kind: str = Field(default="info")
    category: str | None = Field(default=None, max_length=64)
    link: str | None = Field(default=None, max_length=500)


async def _workspace_for_internal(user_id: int, raw_workspace_id: str | None) -> str:
    workspace_id = (raw_workspace_id or "").strip().lower() or None
    async with get_session() as session:
        ws = await resolve_workspace(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    return ws.id


@router.get("")
async def agent_list_notifications(
    limit: int = Query(default=20, ge=1, le=200),
    user: User = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> dict:
    workspace_id = await _workspace_for_internal(user.id, x_workspace_id)
    items = await list_notifications(
        user.id,
        workspace_id=workspace_id,
        limit=limit,
        unread_only=True,
    )
    count = await unread_count(user.id, workspace_id=workspace_id)
    return {"items": items, "unread_count": count}


@router.post("")
async def agent_post_notification(
    payload: AgentNotificationIn,
    user: User = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> dict:
    workspace_id = await _workspace_for_internal(user.id, x_workspace_id)
    try:
        item = await create_notification(
            user.id,
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
