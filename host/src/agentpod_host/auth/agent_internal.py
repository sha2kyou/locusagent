"""校验来自用户 Agent 容器的 X-Internal-Token。"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status
from sqlalchemy import select

from ..db import User, get_session
from ..security import decrypt_str


async def require_agent_internal(
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
    x_user_id: str = Header(default="", alias="X-User-Id"),
) -> User:
    if not x_internal_token or not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user") from exc

    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.internal_token_enc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    expected = decrypt_str(user.internal_token_enc)
    if not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return user
