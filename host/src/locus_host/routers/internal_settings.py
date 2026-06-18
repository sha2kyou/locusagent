"""Agent internal settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from locus_shared.settings_store import get_app_locale, get_app_timezone

from ..auth.agent_internal import require_agent_internal
from ..llm_models import ModelRole, resolve_model

router = APIRouter(prefix="/internal/settings", tags=["internal-settings"])


@router.get("/locale")
async def agent_read_locale(_auth: None = Depends(require_agent_internal)) -> dict:
    return {"locale": get_app_locale()}


@router.get("/timezone")
async def agent_read_timezone(_auth: None = Depends(require_agent_internal)) -> dict:
    return {"timezone": get_app_timezone()}


@router.get("/model")
async def agent_resolve_model(
    role: ModelRole = Query(...),
    _auth: None = Depends(require_agent_internal),
) -> dict:
    return {"model": resolve_model(role)}
