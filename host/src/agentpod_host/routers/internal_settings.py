"""Agent internal settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth.agent_internal import require_agent_internal
from ..db import User

router = APIRouter(prefix="/internal/settings", tags=["internal-settings"])


@router.get("/timezone")
async def agent_read_timezone(user: User = Depends(require_agent_internal)) -> dict:
    return {"timezone": user.timezone or "UTC"}

