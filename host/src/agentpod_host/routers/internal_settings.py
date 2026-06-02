"""Agent internal settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth.agent_internal import require_agent_internal
from ..db import User
from ..llm_models import ModelRole, resolve_model

router = APIRouter(prefix="/internal/settings", tags=["internal-settings"])


@router.get("/timezone")
async def agent_read_timezone(user: User = Depends(require_agent_internal)) -> dict:
    return {"timezone": user.timezone or "UTC"}


@router.get("/model")
async def agent_resolve_model(
    role: ModelRole = Query(...),
    user: User = Depends(require_agent_internal),
) -> dict:
    _ = user
    return {"model": resolve_model(role)}

