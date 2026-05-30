"""容器内 internal 路由：resume 钩子等。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import verify_internal_token
from ..core.scheduled_run import ScheduledRunError, run_scheduled_prompt
from ..logging import get_logger
from ..mcp_.client import reconnect_all_mcp_servers

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_token)])
log = get_logger("internal")


class ScheduledRunIn(BaseModel):
    title: str = Field(default="定时任务", max_length=200)
    prompt: str = Field(..., min_length=1, max_length=20000)


@router.post("/resume")
async def agent_resume() -> dict:
    """容器从 pause/stop 恢复后由 host 调用，重建 MCP 连接。"""
    results = await reconnect_all_mcp_servers()
    connected = sum(1 for v in results.values() if v.get("connected"))
    log.info("agent_resume_mcp_reconnected", servers=len(results), connected=connected)
    return {"ok": True, "mcp": results}


@router.post("/scheduled-run")
async def agent_scheduled_run(payload: ScheduledRunIn) -> dict:
    try:
        return await run_scheduled_prompt(title=payload.title, prompt=payload.prompt)
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
