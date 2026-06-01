"""内部代理：限流与审计。"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from .audit import record_event
from .config import get_settings
from .db import get_session
from .logging import get_logger
from .redis_client import get_redis

_SLIDING_WINDOW_MS = 60_000
log = get_logger("internal_proxy_limits")
_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl_seconds = tonumber(ARGV[5])

redis.call("ZREMRANGEBYSCORE", key, 0, now_ms - window_ms)
local count = redis.call("ZCARD", key)
if count >= limit then
  redis.call("EXPIRE", key, ttl_seconds)
  return 0
end
redis.call("ZADD", key, now_ms, member)
redis.call("EXPIRE", key, ttl_seconds)
return 1
"""


async def enforce_internal_rate_limit(*, user_id: int, bucket: str) -> None:
    settings = get_settings()
    limit = settings.internal_rate_limit_per_minute
    if limit <= 0:
        return
    redis = get_redis()
    key = f"rate_limit:internal:{bucket}:user:{user_id}"
    now_ms = int(time.time() * 1000)
    member = f"{now_ms}-{uuid.uuid4().hex}"
    ttl_seconds = max(120, int((_SLIDING_WINDOW_MS / 1000) * 2))
    try:
        allowed = await redis.eval(
            _SCRIPT,
            1,
            key,
            now_ms,
            _SLIDING_WINDOW_MS,
            limit,
            member,
            ttl_seconds,
        )
    except RedisError as exc:
        log.warning("internal_rate_limit_redis_unavailable", user_id=user_id, bucket=bucket, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="rate limiter unavailable",
        ) from exc
    if int(allowed or 0) != 1:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="internal proxy rate limit exceeded",
        )


async def audit_internal_proxy(
    event: str,
    *,
    user_id: int,
    detail: dict[str, Any] | None = None,
) -> None:
    async with get_session() as session:
        await record_event(session, event, user_id=user_id, detail=detail)
