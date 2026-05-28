"""用户设置：LLM BYOK、模型选择。

保存后由本路由在后台触发容器创建或重建（配置变更时 force_recreate）。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select

from ..audit import record_event
from ..auth import AuthContext, require_session
from ..db import ContainerStatus, User, get_session
from ..logging import get_logger
from ..orchestrator import ensure_user_container
from ..security import decrypt_str, encrypt_str

router = APIRouter(prefix="/api/settings", tags=["settings"])
log = get_logger("settings")

ProvisionAction = Literal["none", "starting", "applying"]


class LLMConfigIn(BaseModel):
    base_url: HttpUrl = Field(..., description="OpenAI 兼容的 base_url")
    api_key: str | None = Field(
        default=None,
        min_length=8,
        description="LLM API Key；已配置用户留空表示不修改",
    )
    model: str = Field(default="gpt-4o", min_length=1)


class LLMConfigOut(BaseModel):
    base_url: str | None
    model: str
    configured: bool
    provision_action: ProvisionAction = "none"


def _llm_config_changed(
    user: User,
    *,
    base_url: str,
    model: str,
    new_api_key_plain: str | None,
) -> bool:
    if user.llm_api_key_enc is None:
        return True
    if user.llm_base_url != base_url:
        return True
    if user.llm_model != model:
        return True
    if new_api_key_plain is not None:
        old_key = decrypt_str(user.llm_api_key_enc)
        if new_api_key_plain != old_key:
            return True
    return False


def _needs_force_recreate(user: User, config_changed: bool) -> bool:
    if not config_changed or user.llm_api_key_enc is None:
        return False
    status = ContainerStatus(user.container_status)
    return status in (
        ContainerStatus.RUNNING,
        ContainerStatus.PAUSED,
        ContainerStatus.STOPPED,
    )


def _resolve_provision_action(user: User, *, config_changed: bool) -> ProvisionAction:
    if not config_changed:
        return "none"
    if _needs_force_recreate(user, config_changed):
        return "applying"
    return "starting"


@router.get("/llm", response_model=LLMConfigOut)
async def read_llm(ctx: AuthContext = Depends(require_session)) -> LLMConfigOut:
    user = ctx.user
    return LLMConfigOut(
        base_url=user.llm_base_url,
        model=user.llm_model,
        configured=user.llm_api_key_enc is not None,
    )


@router.put("/llm", response_model=LLMConfigOut)
async def save_llm(
    payload: LLMConfigIn,
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_session),
) -> LLMConfigOut:
    user = ctx.user
    api_key_plain = (payload.api_key or "").strip() or None

    if user.llm_api_key_enc is None and api_key_plain is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="首次配置必须填写 LLM API Key",
        )
    if api_key_plain is not None and (
        api_key_plain.startswith("apod_") or api_key_plain.startswith("gwzz_")
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="agent_api_key 不能作为 LLM API Key",
        )

    base_url = str(payload.base_url)
    config_changed = _llm_config_changed(
        user,
        base_url=base_url,
        model=payload.model,
        new_api_key_plain=api_key_plain,
    )
    provision_action = _resolve_provision_action(user, config_changed=config_changed)
    force_recreate = provision_action == "applying"

    async with get_session() as session:
        stmt = select(User).where(User.id == user.id)
        db_user = (await session.execute(stmt)).scalar_one()
        db_user.llm_base_url = base_url
        db_user.llm_model = payload.model
        if api_key_plain is not None:
            db_user.llm_api_key_enc = encrypt_str(api_key_plain)
        await record_event(
            session,
            "llm.configured",
            user_id=db_user.id,
            detail={
                "base_url": base_url,
                "model": payload.model,
                "provision_action": provision_action,
            },
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    if provision_action != "none":

        async def _spawn() -> None:
            try:
                await ensure_user_container(user.id, force_recreate=force_recreate)
            except Exception as exc:
                log.error(
                    "llm_save_provision_failed",
                    user_id=user.id,
                    force_recreate=force_recreate,
                    error=str(exc),
                )

        background_tasks.add_task(_spawn)

    return LLMConfigOut(
        base_url=base_url,
        model=payload.model,
        configured=True,
        provision_action=provision_action,
    )
