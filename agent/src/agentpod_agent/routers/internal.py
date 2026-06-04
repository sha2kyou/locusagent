"""容器内 internal 路由：resume 钩子等。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import verify_internal_token
from ..core.scheduled_run import ScheduledRunError, run_scheduled_prompt
from ..logging import get_logger
from ..mcp_.client import reconnect_all_mcp_servers_for_workspace, sync_mcp_tools_for_workspace
from ..workspace import for_each_workspace, get_workspace_id, iter_workspace_ids, set_workspace_id
from ..workspace_runtime import (
    disconnect_mcp_server_runtime,
    invalidate_mcp_runtime,
    mark_mcp_runtime_ready,
    refresh_mcp_server,
)

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_token)])
log = get_logger("internal")


class ScheduledRunIn(BaseModel):
    title: str = Field(default="定时任务", max_length=200)
    prompt: str = Field(..., min_length=1, max_length=20000)
    task_id: int | None = Field(default=None, ge=1)


class McpReconnectIn(BaseModel):
    server_name: str = Field(..., min_length=1, max_length=128)


class McpDisconnectIn(BaseModel):
    server_name: str = Field(..., min_length=1, max_length=128)


@router.post("/mcp/reconnect")
async def mcp_reconnect(payload: McpReconnectIn) -> dict:
    """Host OAuth 回调后通知 Agent 重连指定 MCP 服。"""
    runtime = await refresh_mcp_server(get_workspace_id(), payload.server_name.strip())
    return {"ok": True, "server": payload.server_name, "runtime": runtime}


@router.post("/mcp/disconnect")
async def mcp_disconnect(payload: McpDisconnectIn) -> dict:
    """OAuth 断开或撤销凭据后断开 Agent 侧会话。"""
    ok = await disconnect_mcp_server_runtime(get_workspace_id(), payload.server_name.strip())
    return {"ok": ok, "server": payload.server_name}


@router.post("/resume")
async def agent_resume() -> dict:
    """容器从 pause/stop 恢复后由 host 调用，重建各工作区 MCP 连接。"""
    results: dict[str, object] = {}

    async def _reconnect(wid: str) -> None:
        set_workspace_id(wid)
        invalidate_mcp_runtime(wid)
        results[wid] = await reconnect_all_mcp_servers_for_workspace(wid)
        await sync_mcp_tools_for_workspace(wid)
        mark_mcp_runtime_ready(wid)

    await for_each_workspace(_reconnect)
    connected = sum(
        1
        for per_ws in results.values()
        if isinstance(per_ws, dict)
        for v in per_ws.values()
        if isinstance(v, dict) and v.get("connected")
    )
    log.info(
        "agent_resume_mcp_reconnected",
        workspaces=len(results),
        connected=connected,
    )
    return {"ok": True, "workspaces": len(iter_workspace_ids()), "mcp": results}


@router.get("/scheduled-run-status/{session_id}")
async def scheduled_run_status(session_id: str) -> dict:
    from ..core.persistence import get_active_run, get_last_assistant_text, get_latest_run

    sid = str(session_id or "").strip()
    if not sid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="session_id required")
    active = await get_active_run(sid)
    if active and str(active.get("status") or "") == "running":
        return {"status": "running", "session_id": sid}
    latest = await get_latest_run(sid)
    if latest is None:
        return {"status": "empty", "session_id": sid}
    run_status = str(latest.get("status") or "")
    if run_status == "completed":
        return {
            "status": "completed",
            "session_id": sid,
            "final_text": await get_last_assistant_text(sid),
        }
    if run_status == "failed":
        return {
            "status": "failed",
            "session_id": sid,
            "error": str(latest.get("error_message") or ""),
        }
    return {"status": "empty", "session_id": sid}


@router.post("/scheduled-run")
async def agent_scheduled_run(payload: ScheduledRunIn) -> dict:
    try:
        return await run_scheduled_prompt(
            title=payload.title,
            prompt=payload.prompt,
            task_id=payload.task_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ScheduledRunError as exc:
        log.warning("scheduled_run_failed", session_id=exc.session_id, error=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": str(exc), "session_id": exc.session_id},
        ) from exc
    except Exception as exc:
        log.warning("scheduled_run_failed", error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
