"""签名 Cookie session：单用户打开即用。"""

from __future__ import annotations

import secrets
from functools import lru_cache

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import get_settings

SESSION_COOKIE_NAME = "apod_session"
SESSION_MAX_AGE = 7 * 24 * 3600
SESSION_SALT = "apod.session.v1"
MCP_OAUTH_STATE_MAX_AGE = 600
MCP_OAUTH_STATE_SALT = "apod.mcp.oauth.state.v1"


@lru_cache
def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET 未配置")
    return URLSafeTimedSerializer(settings.session_secret, salt=SESSION_SALT)


@lru_cache
def _mcp_oauth_state_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET 未配置")
    return URLSafeTimedSerializer(settings.session_secret, salt=MCP_OAUTH_STATE_SALT)


def _cookie_secure() -> bool:
    return get_settings().public_base_url.startswith("https://")


def issue_session(response: Response) -> None:
    token = _serializer().dumps({"auth": True})
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def is_valid_session_token(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        payload = _serializer().loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and payload.get("auth") is True


def read_session(request: Request) -> bool:
    return is_valid_session_token(request.cookies.get(SESSION_COOKIE_NAME))


def issue_mcp_oauth_state(*, workspace_id: str, server_name: str) -> str:
    return _mcp_oauth_state_serializer().dumps(
        {"wid": workspace_id, "srv": server_name, "n": secrets.token_urlsafe(16)}
    )


def verify_mcp_oauth_state(raw: str) -> dict[str, str] | None:
    if not raw:
        return None
    try:
        payload = _mcp_oauth_state_serializer().loads(raw, max_age=MCP_OAUTH_STATE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    wid = str(payload.get("wid") or "").strip()
    srv = str(payload.get("srv") or "").strip()
    if not wid or not srv:
        return None
    return {"workspace_id": wid, "server_name": srv}
