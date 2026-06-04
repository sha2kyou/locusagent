"""session_delete：按 id 删除历史会话。"""

from __future__ import annotations

from typing import Any

from ..core.persistence import delete_session, session_lock
from .args import pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


async def _session_delete(args: dict[str, Any]) -> ToolResult:
    from ..core.run_manager import cancel_active_run

    session_id = pick_str(args, "session_id", "id")
    if not session_id:
        raise ToolError("session_id is required (use id from session_recall)")
    lock = await session_lock(session_id)
    async with lock:
        await cancel_active_run(session_id)
        ok = await delete_session(session_id)
    if not ok:
        raise ToolError(f"session not found: {session_id}")
    return ToolResult(content=f"session#{session_id} deleted", metadata={"session_id": session_id})


register_builtin(
    Tool(
        name="session_delete",
        description="按 session_id 删除历史会话及其消息。id 来自 session_recall / session_search。",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话 id（session_recall 返回的 session_id）。",
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
        handler=_session_delete,
    )
)
