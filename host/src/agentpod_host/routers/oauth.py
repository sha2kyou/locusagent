"""GitHub OAuth：login → 重定向 GitHub；callback → 校验 state → upsert 用户 → 签发 session。

关键约束：
- state：secrets.token_urlsafe(32)，写短时签名 cookie，回调比对后清除。
- scope 最小化：仅 `read:user`。
- access_token 仅用于一次拉取用户信息，**不入库**。
- 新用户首次登录时生成 agent_api_key 明文一次性返回，落库仅哈希。
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ..audit import record_event
from ..auth.session import (
    clear_state_cookie,
    issue_apikey_flash,
    issue_session,
    issue_state_cookie,
    read_state_cookie,
)
from ..config import get_settings
from ..db import ContainerStatus, ProvisionStatus, User, get_session
from ..logging import get_logger
from ..security import generate_agent_api_key, hash_agent_api_key
from ..workspaces import ensure_default_workspace

router = APIRouter(prefix="/api/oauth/github", tags=["oauth"])
log = get_logger("oauth")

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"
SCOPE = "read:user"


@router.get("/login")
async def github_login() -> RedirectResponse:
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="OAuth not configured")
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "scope": SCOPE,
        "state": state,
        "allow_signup": "true",
    }
    response = RedirectResponse(f"{GITHUB_AUTHORIZE}?{urlencode(params)}")
    issue_state_cookie(response, state)
    return response


@router.get("/callback")
async def github_callback(request: Request, code: str = "", state: str = ""):
    settings = get_settings()
    expected_state = read_state_cookie(request)
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid state")
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="missing code")

    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            GITHUB_TOKEN,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="github token exchange failed")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="github token missing")

        user_resp = await client.get(
            GITHUB_USER,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if user_resp.status_code != 200:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="github user fetch failed")
        gh_user = user_resp.json()

    github_id = int(gh_user["id"])
    username = str(gh_user.get("login") or gh_user.get("name") or f"gh-{github_id}")
    avatar_url = gh_user.get("avatar_url")

    new_api_key_plain: str | None = None
    async with get_session() as session:
        stmt = select(User).where(User.github_id == github_id)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            new_api_key_plain = generate_agent_api_key()
            user = User(
                github_id=github_id,
                username=username,
                avatar_url=avatar_url,
                agent_api_key_hash=hash_agent_api_key(new_api_key_plain),
            )
            session.add(user)
            await session.flush()
            await record_event(
                session,
                "user.created",
                user_id=user.id,
                detail={"username": username},
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        else:
            if existing.deleted_at is not None:
                existing.deleted_at = None
                existing.internal_token_enc = None
                existing.container_id = None
                existing.network_name = None
                existing.volume_name = None
                existing.container_status = ContainerStatus.ABSENT.value
                existing.provision_status = ProvisionStatus.PENDING.value
                new_api_key_plain = generate_agent_api_key()
                existing.agent_api_key_hash = hash_agent_api_key(new_api_key_plain)
            existing.username = username
            existing.avatar_url = avatar_url
            user = existing
            await record_event(
                session,
                "user.login",
                user_id=user.id,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        user_id = user.id
        await ensure_default_workspace(session, user_id)

    response = RedirectResponse("/chat", status_code=status.HTTP_302_FOUND)
    issue_session(response, user_id)
    clear_state_cookie(response)
    if new_api_key_plain is not None:
        issue_apikey_flash(response, new_api_key_plain)
    log.info("oauth_callback_ok", user_id=user_id, new_user=new_api_key_plain is not None)
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("apod_session", path="/")
    return response
