"""Agent 侧操作日志：自动附带当前工作区 ID。"""

from __future__ import annotations

from typing import Any

from locus_shared.activity_log import record_activity as _record_activity


def record_activity(
    category: str,
    action: str,
    message: str,
    *,
    workspace_id: str | None = None,
    level: str = "info",
    detail: dict[str, Any] | None = None,
) -> int:
    wid = workspace_id
    if not wid:
        try:
            from .workspace import get_workspace_id

            raw = get_workspace_id()
            wid = raw or None
        except Exception:
            wid = None
    return _record_activity(
        category,
        action,
        message,
        workspace_id=wid,
        level=level,
        detail=detail,
    )


__all__ = ["record_activity"]
