"""v1 会话查询相关路由。"""

from __future__ import annotations

from fastapi import APIRouter

from ..core import get_active_run, list_messages, list_sessions

router = APIRouter()


@router.get("/sessions")
async def get_sessions() -> dict:
    items = await list_sessions(limit=100)
    return {"items": items}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> dict:
    items = await list_messages(session_id)
    return {"items": items}


@router.get("/sessions/{session_id}/active-run")
async def get_session_active_run(session_id: str) -> dict:
    run = await get_active_run(session_id)
    return {"run": run}
