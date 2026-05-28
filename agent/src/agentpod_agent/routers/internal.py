"""容器内 internal 路由：resume 钩子等。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import verify_internal_token
from ..logging import get_logger
from ..mcp_.client import reconnect_all_mcp_servers

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_token)])
log = get_logger("internal")


@router.post("/resume")
async def agent_resume() -> dict:
    """容器从 pause/stop 恢复后由 host 调用，重建 MCP 连接。"""
    results = await reconnect_all_mcp_servers()
    connected = sum(1 for v in results.values() if v.get("connected"))
    log.info("agent_resume_mcp_reconnected", servers=len(results), connected=connected)
    return {"ok": True, "mcp": results}
