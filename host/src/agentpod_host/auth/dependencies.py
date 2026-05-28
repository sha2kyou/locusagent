"""FastAPI 鉴权依赖：session / bearer 互斥。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request, status
from sqlalchemy import select

from ..db import User, get_session
from ..security import hash_agent_api_key
from .session import read_session

AuthType = Literal["session", "bearer"]


@dataclass(slots=True)
class AuthContext:
    user: User
    auth_type: AuthType


async def _load_user_by_id(user_id: int) -> User | None:
    async with get_session() as session:
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def _load_user_by_api_key_hash(key_hash: str) -> User | None:
    async with get_session() as session:
        stmt = select(User).where(
            User.agent_api_key_hash == key_hash, User.deleted_at.is_(None)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def require_session(request: Request) -> AuthContext:
    user_id = read_session(request)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing session")
    user = await _load_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session invalid")
    return AuthContext(user=user, auth_type="session")


async def require_bearer(request: Request) -> AuthContext:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer")
    token = header[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="empty bearer")
    user = await _load_user_by_api_key_hash(hash_agent_api_key(token))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
    return AuthContext(user=user, auth_type="bearer")


async def resolve_auth(request: Request) -> AuthContext | None:
    """中间件用：尝试任一鉴权方式，失败返回 None（不抛异常）。"""
    user_id = read_session(request)
    if user_id is not None:
        user = await _load_user_by_id(user_id)
        if user is not None:
            return AuthContext(user=user, auth_type="session")
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            user = await _load_user_by_api_key_hash(hash_agent_api_key(token))
            if user is not None:
                return AuthContext(user=user, auth_type="bearer")
    return None
