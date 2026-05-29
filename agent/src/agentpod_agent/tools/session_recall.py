"""历史会话召回工具：RAG + FTS hybrid 检索，或查看会话列表/消息。"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..db import conn_scope, run_in_thread
from ..memory.embedder import EmbeddingUnavailable, embed_text
from ..recall import fts_search
from ..recall.pipeline import SHORT_QUERY_MAX_LEN, merge_hybrid_keys
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


def _message_from_row(row: dict[str, Any], *, query: str, score: float | None = None) -> dict[str, Any]:
    return {
        "session_id": str(row.get("session_id") or ""),
        "session_title": str(row.get("session_title") or "新对话"),
        "session_updated_at": row.get("session_updated_at"),
        "message_id": row.get("id"),
        "role": str(row.get("role") or ""),
        "created_at": row.get("created_at"),
        "score": round(float(score or 0.0), 4) if score is not None else None,
        "snippet": _snippet(str(row.get("content") or ""), query),
    }


async def _like_fallback_recall(
    query: str,
    top_k: int,
    *,
    scan_sessions: int,
    per_session_messages: int,
) -> list[dict[str, Any]]:
    """短 query 或 hybrid 无命中时，LIKE 扫描最近会话。"""
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
                _message_from_row(
                    {
                        "id": r.get("id"),
                        "session_id": sid,
                        "session_title": title,
                        "session_updated_at": updated_at,
                        "role": role,
                        "created_at": r.get("created_at"),
                        "content": content,
                    },
                    query=query,
                    score=float(score),
                )
            )
    hits.sort(
        key=lambda x: (
            int(x.get("score") or 0),
            str(x.get("session_updated_at") or ""),
            int(x.get("message_id") or 0),
        ),
        reverse=True,
    )
    return hits[:top_k]


async def _hybrid_message_recall(query: str, top_k: int) -> list[dict[str, Any]]:
    k = max(1, top_k)
    fetch_k = k * 2
    max_distance = get_settings().recall_max_distance
    q_blob: bytes | None = None
    try:
        q_blob = await embed_text(query)
    except EmbeddingUnavailable:
        q_blob = None

    _FROM = """
        FROM messages_fts
        JOIN messages m ON m.id = messages_fts.rowid
        JOIN sessions s ON s.id = m.session_id
    """
    _SELECT = """
        CAST(m.id AS TEXT) AS id, m.session_id, m.role, m.content, m.created_at,
        s.title AS session_title, s.updated_at AS session_updated_at
    """

    async def _fts_keys() -> list[str]:
        hits = await fts_search(
            fts_table="messages_fts",
            from_clause=_FROM,
            select_columns=_SELECT,
            where_extra="m.role IN ('user', 'assistant')",
            query=query,
            top_k=fetch_k,
            min_query_len=3,
        )
        return [str(h["id"]) for h in hits]

    async def _vec_keys() -> list[str]:
        if q_blob is None:
            return []

        def _do() -> list[str]:
            with conn_scope(load_vec=True) as c:
                rows = c.execute(
                    """
                    SELECT CAST(m.id AS TEXT) AS id, vec_distance_cosine(m.embedding, ?) AS score
                    FROM messages m
                    WHERE m.embedding_state = 'ready' AND m.role IN ('user', 'assistant')
                    ORDER BY score ASC
                    LIMIT ?
                    """,
                    (q_blob, fetch_k),
                ).fetchall()
                return [
                    str(r["id"])
                    for r in rows
                    if r["score"] is not None and r["score"] <= max_distance
                ]

        return await run_in_thread(_do)

    vec_ranked = await _vec_keys() if q_blob is not None else []
    fts_ranked = await _fts_keys()
    merged_keys, scores = await merge_hybrid_keys(top_k=k, vec_ranked=vec_ranked, fts_ranked=fts_ranked)
    if not merged_keys:
        return []

    def _fetch() -> list[dict[str, Any]]:
        placeholders = ",".join("?" * len(merged_keys))
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                f"""
                SELECT m.id, m.session_id, m.role, m.content, m.created_at,
                       s.title AS session_title, s.updated_at AS session_updated_at
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE CAST(m.id AS TEXT) IN ({placeholders})
                """,
                merged_keys,
            ).fetchall()
        by_id = {str(r["id"]): dict(r) for r in rows}
        return [by_id[key] for key in merged_keys if key in by_id]

    rows = await run_in_thread(_fetch)
    return [
        _message_from_row(row, query=query, score=scores.get(str(row.get("id")), 0.0))
        for row in rows
    ]


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
    scan_sessions = _clamp_int(args.get("scan_sessions"), default=20, min_v=1, max_v=100)
    per_session_messages = _clamp_int(args.get("per_session_messages"), default=80, min_v=1, max_v=500)

    picked = await _hybrid_message_recall(query, top_k)
    if not picked and len(query) <= SHORT_QUERY_MAX_LEN:
        picked = await _like_fallback_recall(
            query,
            top_k,
            scan_sessions=scan_sessions,
            per_session_messages=per_session_messages,
        )

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
        description="历史会话召回：recall(RAG+FTS 混合检索) / sessions(列会话) / messages(查会话消息)。",
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
