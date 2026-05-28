"""审计日志：写入 audit_logs 表 + 结构化日志双写。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .db import AuditLog
from .logging import get_logger

log = get_logger("audit")


async def record_event(
    session: AsyncSession,
    event: str,
    *,
    user_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        event=event,
        detail=detail,
        ip=ip,
        user_agent=user_agent,
    )
    session.add(entry)
    log.info(event, kind="audit", user_id=user_id, ip=ip, detail=detail)
