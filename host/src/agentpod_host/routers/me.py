"""当前用户相关接口（session 鉴权）。

包含：
- GET /api/me                  当前用户摘要
- GET /api/me/api-key/flash    一次性读取新生成的 agent_api_key 明文（cookie 销毁）
- POST /api/me/api-key/rotate  轮换 agent_api_key（明文一次性返回）
- DELETE /api/me               删除账户（需 confirm_username）
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..audit import record_event
from ..auth import AuthContext, clear_session, consume_apikey_flash, require_session
from ..config import get_settings
from ..db import User, get_session
from ..logging import get_logger
from ..orchestrator import teardown_container
from ..security import generate_agent_api_key, hash_agent_api_key
from ..workspaces import requested_workspace_id, resolve_workspace

router = APIRouter(prefix="/api/me", tags=["me"])
log = get_logger("me")


class AccountDeleteIn(BaseModel):
    confirm_username: str = Field(..., min_length=1)


@router.get("")
async def me(request: Request, ctx: AuthContext = Depends(require_session)) -> dict:
    user = ctx.user
    settings = get_settings()
    async with get_session() as session:
        workspace = await resolve_workspace(
            session,
            user_id=user.id,
            workspace_id=requested_workspace_id(request),
        )
    return {
        "id": user.id,
        "username": user.username,
        "avatar_url": user.avatar_url,
        "current_workspace_id": workspace.id,
        "container_status": user.container_status,
        "provision_status": user.provision_status,
        "llm_configured": user.llm_api_key_enc is not None,
        "llm_base_url": user.llm_base_url,
        "llm_model": user.llm_model,
        "agent_api_key_configured": bool(user.agent_api_key_hash),
        "attachment_max_bytes": settings.attachment_max_bytes,
    }


@router.get("/api-key/flash")
async def read_apikey_flash(
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    plain = consume_apikey_flash(request, response)
    return {"api_key": plain}


@router.post("/api-key/rotate")
async def rotate_apikey(
    request: Request,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    new_plain = generate_agent_api_key()
    new_hash = hash_agent_api_key(new_plain)
    async with get_session() as session:
        stmt = select(User).where(User.id == ctx.user.id)
        user = (await session.execute(stmt)).scalar_one()
        user.agent_api_key_hash = new_hash
        await record_event(
            session,
            "apikey.rotated",
            user_id=user.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    return {"api_key": new_plain}


@router.delete("")
async def delete_account(
    payload: AccountDeleteIn,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(require_session),
) -> dict:
    """软删账户：清理容器/volume，清除密钥，注销 session。"""
    if payload.confirm_username.strip() != ctx.user.username:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="confirm_username mismatch",
        )

    user_id = ctx.user.id
    async with get_session() as session:
        stmt = select(User).where(User.id == user_id)
        user = (await session.execute(stmt)).scalar_one()
        user.deleted_at = datetime.now(timezone.utc)
        user.llm_api_key_enc = None
        user.llm_base_url = None
        user.internal_token_enc = None
        user.container_id = None
        user.network_name = None
        user.volume_name = None
        user.agent_api_key_hash = hash_agent_api_key(generate_agent_api_key())
        await record_event(
            session,
            "user.deleted",
            user_id=user_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    try:
        await teardown_container(user_id, remove_volume=True)
    except Exception as exc:
        log.warning("delete_account_teardown_failed", user_id=user_id, error=str(exc))

    clear_session(response)
    response.delete_cookie("apod_apikey_flash", path="/")
    log.info("account_deleted", user_id=user_id)
    return {"ok": True}
