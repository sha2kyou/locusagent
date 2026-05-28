"""签名 Cookie session：仅承载 user_id + 签发时间。

Cookie 属性：HttpOnly + Secure(生产) + SameSite=Lax + Max-Age 7d。
SESSION_SECRET 与 ENCRYPTION_KEY 互斥。
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import get_settings

SESSION_COOKIE_NAME = "apod_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 天
SESSION_SALT = "apod.session.v1"


@lru_cache
def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET 未配置")
    return URLSafeTimedSerializer(settings.session_secret, salt=SESSION_SALT)


def issue_session(response: Response, user_id: int) -> None:
    serializer = _serializer()
    token = serializer.dumps({"uid": user_id})
    settings = get_settings()
    secure = settings.public_base_url.startswith("https://")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def read_session(request: Request) -> int | None:
    """从 cookie 解出 user_id；签名失败/过期返回 None。"""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = _serializer().loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    uid = payload.get("uid")
    return int(uid) if isinstance(uid, int) else None


def issue_state_cookie(response: Response, state: str) -> None:
    """OAuth state：5 分钟短时 cookie，回调比对后立即清除。"""
    settings = get_settings()
    secure = settings.public_base_url.startswith("https://")
    response.set_cookie(
        "apod_oauth_state",
        state,
        max_age=300,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def read_state_cookie(request: Request) -> str | None:
    return request.cookies.get("apod_oauth_state")


def clear_state_cookie(response: Response) -> None:
    response.delete_cookie("apod_oauth_state", path="/")


FLASH_COOKIE_NAME = "apod_apikey_flash"
FLASH_MAX_AGE = 120  # 2 分钟内必须读取
FLASH_SALT = "apod.apikey-flash.v1"


@lru_cache
def _flash_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET 未配置")
    return URLSafeTimedSerializer(settings.session_secret, salt=FLASH_SALT)


def issue_apikey_flash(response: Response, api_key_plain: str) -> None:
    """一次性 flash cookie，承载新生成的 agent_api_key 明文。

    HttpOnly：前端必须通过专用接口读取，避免 XSS 直接抓取。
    """
    settings = get_settings()
    secure = settings.public_base_url.startswith("https://")
    token = _flash_serializer().dumps({"k": api_key_plain})
    response.set_cookie(
        FLASH_COOKIE_NAME,
        token,
        max_age=FLASH_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def consume_apikey_flash(request: Request, response: Response) -> str | None:
    """读取并立即清除 flash cookie。"""
    raw = request.cookies.get(FLASH_COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = _flash_serializer().loads(raw, max_age=FLASH_MAX_AGE)
    except (BadSignature, SignatureExpired):
        response.delete_cookie(FLASH_COOKIE_NAME, path="/")
        return None
    response.delete_cookie(FLASH_COOKIE_NAME, path="/")
    if isinstance(payload, dict):
        value = payload.get("k")
        return value if isinstance(value, str) else None
    return None
