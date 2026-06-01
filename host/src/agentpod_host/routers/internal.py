"""内部端点：手动触发容器创建（幂等）。

鉴权：session（仅本人）。首次访问工作区时代理会自动 provision。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from ..audit import record_event
from ..auth import AuthContext, require_session
from ..db import ContainerStatus, get_session
from ..logging import get_logger
from ..orchestrator import ensure_user_container
from ..orchestrator.agent_env import require_llm_configured

router = APIRouter(prefix="/internal/containers", tags=["internal"])
log = get_logger("internal")


@router.post("/ensure")
async def ensure(
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    user = ctx.user
    try:
        require_llm_configured()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    current = ContainerStatus(user.container_status)
    if current == ContainerStatus.RUNNING:
        return {"status": current.value, "provision_status": user.provision_status}

    async with get_session() as session:
        await record_event(
            session,
            "container.ensure_requested",
            user_id=user.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    async def _spawn() -> None:
        try:
            await ensure_user_container(user.id)
        except Exception as exc:  # 已在 lifecycle 内打日志/写状态
            log.error("ensure_user_container_failed", user_id=user.id, error=str(exc))

    background_tasks.add_task(_spawn)
    return {"status": ContainerStatus.CREATING.value, "provision_status": "pending"}
