"""notification_query：查询当前用户的未读通知。"""

from __future__ import annotations

from typing import Any

from ..host_notifications import HostNotificationsError, list_unread_notifications, mark_notification_read
from .args import pick_int
from .base import Tool, ToolError, ToolResult, register_builtin


def _clamp_int(v: Any, *, default: int, min_v: int, max_v: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(min_v, min(max_v, n))


def _item_line(item: dict[str, Any]) -> str:
    nid = item.get("id")
    kind = str(item.get("kind") or "info")
    title = str(item.get("title") or "").strip() or "(untitled)"
    category = str(item.get("category") or "").strip()
    when = str(item.get("created_at") or "")
    prefix = f"[{kind}]"
    if category:
        prefix += f"[{category}]"
    suffix = f" @ {when}" if when else ""
    return f"#{nid} {prefix} {title}{suffix}"


async def _notification_query(args: dict[str, Any]) -> ToolResult:
    limit = _clamp_int(args.get("limit"), default=20, min_v=1, max_v=100)
    query = str(args.get("query", "")).strip().lower()
    include_body = bool(args.get("include_body", False))
    try:
        items, unread = await list_unread_notifications(limit=limit)
    except HostNotificationsError as exc:
        raise ToolError(str(exc)) from exc

    if query:
        items = [
            it
            for it in items
            if query
            in " ".join(
                [
                    str(it.get("title") or ""),
                    str(it.get("body") or ""),
                    str(it.get("category") or ""),
                    str(it.get("kind") or ""),
                ]
            ).lower()
        ]
    if not items:
        return ToolResult(
            content="(no unread notification hits)",
            metadata={"items": [], "unread_count": unread, "query": query},
        )

    lines: list[str] = []
    for it in items:
        lines.append(_item_line(it))
        body = str(it.get("body") or "").strip()
        if include_body and body:
            lines.append(f"  body: {body}")
    return ToolResult(
        content="\n".join(lines),
        metadata={"items": items, "unread_count": unread, "query": query},
    )


register_builtin(
    Tool(
        name="notification_query",
        description="查询当前用户未读通知，可按关键词过滤，支持返回正文。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "limit": {"type": "integer", "default": 20},
                "include_body": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
        handler=_notification_query,
    )
)


async def _notification_mark_read(args: dict[str, Any]) -> ToolResult:
    notification_id = pick_int(args, "id", "notification_id")
    if not notification_id:
        raise ToolError("id is required (use id from notification_query)")
    try:
        ok = await mark_notification_read(notification_id)
    except HostNotificationsError as exc:
        raise ToolError(str(exc)) from exc
    if not ok:
        raise ToolError(f"notification not found: #{notification_id}")
    return ToolResult(
        content=f"notification#{notification_id} marked read",
        metadata={"notification_id": notification_id},
    )


register_builtin(
    Tool(
        name="notification_mark_read",
        description="按 id 将通知标记为已读。id 来自 notification_query。",
        parameters={
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "通知 id（notification_query 返回的 #id）。",
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        handler=_notification_mark_read,
    )
)
