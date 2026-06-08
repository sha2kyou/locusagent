"""校验来自 Agent 容器的 X-Internal-Token。"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from ..config import get_settings


async def require_agent_internal(
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
    authorization: str = Header(default=""),
) -> None:
    token = x_internal_token.strip()
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    expected = get_settings().agent_internal_token.strip()
    if not token or not expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
