"""历史会话召回工具：按关键词检索历史对话，或查看会话列表/消息。"""

from __future__ import annotations

from typing import Any

from ..db import conn_scope, run_in_thread
from .base import Tool, ToolError, ToolResult, register_builtin


def _clamp_int(v: Any, *, default: int, min_v: int, max_v: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(min_v, min(max_v, n))


def _snippet(text: str, query: str, *, radius: int = 48) -> str:
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    q = str(query or "").strip().lower()
    if not q:
        return raw[: radius * 2]
    idx = raw.lower().find(q)
    if idx < 0:
        return raw[: radius * 2]
    start = max(0, idx - radius)
    end = min(len(raw), idx + len(q) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(raw) else ""
    return f"{prefix}{raw[start:end]}{suffix}"


async def _list_sessions(limit: int) -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, title, status, total_tokens, created_at, updated_at "
                "FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def _list_messages(session_id: str) -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, role, content, tool_calls, tool_call_id, run_id, tokens, created_at "
                "FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def _fts_recall(query: str, top_k: int) -> list[dict[str, Any]] | None:
    """trigram FTS5 跨会话关键词检索（bm25 排序）。

    FTS 表不存在或查询异常时返回 None，调用方回退 LIKE 扫描。
    """
    match = '"' + query.replace('"', '""') + '"'

    def _do() -> list[dict[str, Any]] | None:
        with conn_scope(load_vec=False) as c:
            has_fts = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages_fts'"
            ).fetchone()
            if not has_fts:
                return None
            rows = c.execute(
                """
                SELECT m.id, m.session_id, m.role, m.content, m.created_at,
                       s.title AS session_title, s.updated_at AS session_updated_at,
                       bm25(messages_fts) AS rank
                FROM messages_fts
                JOIN messages m ON m.id = messages_fts.rowid
                JOIN sessions s ON s.id = m.session_id
                WHERE messages_fts MATCH ? AND m.role IN ('user', 'assistant')
                ORDER BY rank
                LIMIT ?
                """,
                (match, top_k),
            ).fetchall()
            return [dict(r) for r in rows]

    try:
        return await run_in_thread(_do)
    except Exception:
        return None


async def _session_recall(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action", "recall") or "recall").strip().lower()
    if action == "sessions":
        limit = _clamp_int(args.get("limit"), default=20, min_v=1, max_v=100)
        sessions = await _list_sessions(limit=limit)
        if not sessions:
            return ToolResult(content="(no sessions)")
        lines = [
            f"- {s.get('id')} | {s.get('title') or '新对话'} | {s.get('updated_at') or '-'}"
            for s in sessions
        ]
        return ToolResult(content="\n".join(lines), metadata={"items": sessions})

    if action == "messages":
        session_id = str(args.get("session_id", "")).strip()
        if not session_id:
            raise ToolError("session_id is required for messages")
        limit = _clamp_int(args.get("limit"), default=30, min_v=1, max_v=200)
        rows = await _list_messages(session_id)
        rows = rows[-limit:]
        if not rows:
            return ToolResult(content="(empty session)", metadata={"session_id": session_id, "items": []})
        lines = []
        for r in rows:
            role = str(r.get("role") or "")
            content = " ".join(str(r.get("content") or "").split())
            lines.append(f"[{role}] {content[:240]}")
        return ToolResult(
            content="\n".join(lines),
            metadata={"session_id": session_id, "items": rows},
        )

    if action != "recall":
        raise ToolError(f"unknown action: {action}")

    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required for recall")
    top_k = _clamp_int(args.get("top_k"), default=5, min_v=1, max_v=30)

    picked: list[dict[str, Any]] | None = None

    # 优先 trigram FTS5（query 至少 3 字符，trigram 最小匹配粒度）
    if len(query) >= 3:
        fts_hits = await _fts_recall(query, top_k)
        if fts_hits is not None:
            picked = [
                {
                    "session_id": str(h.get("session_id") or ""),
                    "session_title": str(h.get("session_title") or "新对话"),
                    "session_updated_at": h.get("session_updated_at"),
                    "message_id": h.get("id"),
                    "role": str(h.get("role") or ""),
                    "created_at": h.get("created_at"),
                    "score": round(-float(h.get("rank") or 0.0), 4),
                    "snippet": _snippet(str(h.get("content") or ""), query),
                }
                for h in fts_hits
            ]

    # 回退：短 query 或 FTS 不可用时，LIKE 扫描最近会话
    if picked is None:
        scan_sessions = _clamp_int(args.get("scan_sessions"), default=20, min_v=1, max_v=100)
        per_session_messages = _clamp_int(args.get("per_session_messages"), default=80, min_v=1, max_v=500)
        sessions = await _list_sessions(limit=scan_sessions)
        q_lower = query.lower()
        hits: list[dict[str, Any]] = []
        for s in sessions:
            sid = str(s.get("id") or "")
            if not sid:
                continue
            title = str(s.get("title") or "新对话")
            updated_at = s.get("updated_at")
            rows = await _list_messages(sid)
            for r in reversed(rows[-per_session_messages:]):
                role = str(r.get("role") or "")
                if role not in {"user", "assistant"}:
                    continue
                content = str(r.get("content") or "").strip()
                if not content:
                    continue
                lower = content.lower()
                if q_lower not in lower:
                    continue
                score = lower.count(q_lower) * 5
                if role == "user":
                    score += 1
                hits.append(
                    {
                        "session_id": sid,
                        "session_title": title,
                        "session_updated_at": updated_at,
                        "message_id": r.get("id"),
                        "role": role,
                        "created_at": r.get("created_at"),
                        "score": score,
                        "snippet": _snippet(content, query),
                    }
                )
        hits.sort(
            key=lambda x: (
                int(x.get("score") or 0),
                str(x.get("session_updated_at") or ""),
                int(x.get("message_id") or 0),
            ),
            reverse=True,
        )
        picked = hits[:top_k]

    if not picked:
        return ToolResult(content="(no history hits)", metadata={"items": []})

    lines = [
        (
            f"- [{h['session_title']}]({h['session_id']}) "
            f"[{h['role']}] {h['snippet']}"
        )
        for h in picked
    ]
    return ToolResult(content="\n".join(lines), metadata={"items": picked, "query": query})


register_builtin(
    Tool(
        name="session_recall",
        description="历史会话召回：recall(关键词检索) / sessions(列会话) / messages(查会话消息)。",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["recall", "sessions", "messages"], "default": "recall"},
                "query": {"type": "string"},
                "session_id": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "scan_sessions": {"type": "integer", "default": 20},
                "per_session_messages": {"type": "integer", "default": 80},
                "limit": {"type": "integer", "default": 20},
            },
            "additionalProperties": False,
        },
        handler=_session_recall,
    )
)

