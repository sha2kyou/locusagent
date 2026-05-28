"""内部端点：手动触发容器创建（幂等）。

鉴权：session（仅本人）。常规流程已在 PUT /api/settings/llm 内自动 provision。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from ..audit import record_event
from ..auth import AuthContext, require_session
from ..db import ContainerStatus, get_session
from ..logging import get_logger
from ..orchestrator import ensure_user_container

router = APIRouter(prefix="/internal/containers", tags=["internal"])
log = get_logger("internal")


@router.post("/ensure")
async def ensure(
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    user = ctx.user
    if user.llm_api_key_enc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先在 /settings 配置 LLM API Key",
        )

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
