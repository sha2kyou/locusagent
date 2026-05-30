"""session_search 工具：跨会话检索历史消息。"""

from __future__ import annotations

from typing import Any

from ..recall import SHORT_QUERY_MAX_LEN
from .base import Tool, ToolError, ToolResult, register_builtin
from .session_recall import _hybrid_message_recall, _like_fallback_recall


def _clamp_int(v: Any, *, default: int, min_v: int, max_v: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(min_v, min(max_v, n))


async def _session_search(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required")
    top_k = _clamp_int(args.get("top_k"), default=8, min_v=1, max_v=50)
    scan_sessions = _clamp_int(args.get("scan_sessions"), default=30, min_v=1, max_v=200)
    per_session_messages = _clamp_int(args.get("per_session_messages"), default=100, min_v=1, max_v=500)

    hits = await _hybrid_message_recall(query, top_k)
    if not hits and len(query) <= SHORT_QUERY_MAX_LEN:
        hits = await _like_fallback_recall(
            query,
            top_k,
            scan_sessions=scan_sessions,
            per_session_messages=per_session_messages,
        )
    if not hits:
        return ToolResult(content="(no session hits)", metadata={"items": [], "query": query})

    lines = []
    for h in hits:
        score = h.get("score")
        score_txt = f"{score:.4f} " if isinstance(score, (int, float)) else ""
        lines.append(
            f"- {score_txt}[{h['session_title']}]({h['session_id']}) "
            f"[{h['role']}] {h['snippet']}"
        )
    return ToolResult(content="\n".join(lines), metadata={"items": hits, "query": query})


register_builtin(
    Tool(
        name="session_search",
        description="跨会话检索历史消息，返回最相关命中及片段摘要。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 8},
                "scan_sessions": {"type": "integer", "default": 30},
                "per_session_messages": {"type": "integer", "default": 100},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=_session_search,
    )
)

