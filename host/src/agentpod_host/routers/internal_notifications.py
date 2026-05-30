"""Agent 容器内部回调：写入用户站内通知。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth.agent_internal import require_agent_internal
from ..db import User
from ..notifications import create_notification

router = APIRouter(prefix="/internal/notifications", tags=["internal-notifications"])


class AgentNotificationIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    kind: str = Field(default="info")
    category: str | None = Field(default=None, max_length=64)
    link: str | None = Field(default=None, max_length=500)


@router.post("")
async def agent_post_notification(
    payload: AgentNotificationIn,
    user: User = Depends(require_agent_internal),
) -> dict:
    try:
        item = await create_notification(
            user.id,
            title=payload.title,
            body=payload.body,
            kind=payload.kind,
            category=payload.category,
            link=payload.link,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"item": item}
