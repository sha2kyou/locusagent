"""内部代理：限流。"""

from __future__ import annotations

from locus_shared.memory_cache import enforce_sliding_rate_limit
from fastapi import HTTPException, status

from .config import get_settings
from .logging import get_logger

log = get_logger("internal_proxy_limits")


async def enforce_internal_rate_limit(
    *,
    bucket: str,
    workspace_id: str | None = None,
) -> None:
    settings = get_settings()
    limit = settings.internal_rate_limit_per_minute
    allowed = await enforce_sliding_rate_limit(
        bucket=bucket,
        workspace_id=workspace_id,
        limit=limit,
    )
    if not allowed:
        log.warning(
            "internal_rate_limit_exceeded",
            bucket=bucket,
            workspace_id=workspace_id,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="internal rate limit exceeded",
        )
