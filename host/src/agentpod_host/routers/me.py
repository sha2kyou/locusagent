"""应用会话摘要（session 鉴权）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import AuthContext, require_session
from ..config import get_settings
from ..workspaces import requested_workspace_id, resolve_workspace
from ..db import get_session

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("")
async def me(request: Request, ctx: AuthContext = Depends(require_session)) -> dict:
    _ = ctx
    settings = get_settings()
    async with get_session() as session:
        workspace = await resolve_workspace(
            session,
            workspace_id=requested_workspace_id(request),
        )
    return {
        "current_workspace_id": workspace.id,
        "attachment_max_bytes": settings.attachment_max_bytes,
    }
