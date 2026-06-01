"""Agent 上报用量事件。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..auth.agent_internal import require_agent_internal
from ..db import User, get_session
from ..internal_proxy_limits import enforce_internal_rate_limit
from ..usage import UsageEventIn, record_usage_events
from ..workspaces import resolve_workspace

router = APIRouter(prefix="/internal/usage", tags=["internal-usage"])


class UsageEventsIn(BaseModel):
    events: list[UsageEventIn] = Field(default_factory=list, max_length=50)


async def _workspace_for_internal(user_id: int, raw_workspace_id: str | None) -> str:
    workspace_id = (raw_workspace_id or "").strip().lower() or None
    async with get_session() as session:
        ws = await resolve_workspace(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    return ws.id


@router.post("/events")
async def post_usage_events(
    payload: UsageEventsIn,
    user: User = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> dict:
    if not payload.events:
        return {"ok": True, "count": 0}
    await enforce_internal_rate_limit(user_id=user.id, bucket="usage")
    try:
        workspace_id = await _workspace_for_internal(user.id, x_workspace_id)
    except HTTPException:
        raise
    async with get_session() as session:
        count = await record_usage_events(
            session,
            user_id=user.id,
            workspace_id=workspace_id,
            events=payload.events,
        )
    return {"ok": True, "count": count}
