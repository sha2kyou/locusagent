"""FastAPI 鉴权依赖：session。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request, status

from .auto_session import bootstrap_session

AuthType = Literal["session"]


@dataclass(slots=True)
class AuthContext:
    auth_type: AuthType


async def require_session(request: Request) -> AuthContext:
    if not await bootstrap_session(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing session")
    return AuthContext(auth_type="session")
