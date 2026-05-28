"""容器内 X-Internal-Token 校验依赖。

容器对外仅暴露 /health 不鉴权，其他端点必须 HMAC 比对。
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def verify_internal_token(x_internal_token: str = Header(default="")) -> None:
    settings = get_settings()
    expected = settings.internal_token
    if not expected or not x_internal_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    if not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
