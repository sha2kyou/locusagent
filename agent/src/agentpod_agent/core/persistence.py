"""会话/消息持久化（SQLite，单 writer 通过 asyncio.to_thread 串行）。"""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any

from ..db import conn_scope, run_in_thread

_session_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def session_lock(session_id: str) -> asyncio.Lock:
    async with _locks_guard:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[session_id] = lock
        return lock


def _new_session_id() -> str:
    return f"sess_{secrets.token_urlsafe(12)}"


def _new_run_id() -> str:
    return f"run_{secrets.token_urlsafe(10)}"


def _new_response_id() -> str:
    return f"resp_{secrets.token_urlsafe(12)}"


def _is_legacy_event_meta(tool_calls: Any) -> bool:
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    first = tool_calls[0]
    return isinstance(first, dict) and "event_type" in first


def _is_openai_tool_calls(tool_calls: Any) -> bool:
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    first = tool_calls[0]
    return isinstance(first, dict) and ("function" in first or first.get("type") == "function")


async def create_session(title: str | None = None) -> str:
    sid = _new_session_id()

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO sessions(id, title) VALUES(?, ?)",
                (sid, title or "新对话"),
            )

    await run_in_thread(_do)
    return sid


async def upsert_session_meta(
    session_id: str,
    *,
    title: str | None = None,
    tokens_delta: int = 0,
    status: str | None = None,
) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            updates = ["updated_at = datetime('now')"]
            params: list[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if tokens_delta:
                updates.append("total_tokens = total_tokens + ?")
                params.append(tokens_delta)
            params.append(session_id)
            sql = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"
            c.execute(sql, params)

    await run_in_thread(_do)


STALE_RUN_SECONDS = 600


async def expire_stale_runs(
    session_id: str | None = None,
    *,
    max_age_seconds: int = STALE_RUN_SECONDS,
) -> int:
    """将超时未更新的 running run 标为 failed，返回清理数量。"""

    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            if session_id:
                cur = c.execute(
                    "UPDATE runs SET status='failed', error_message='stale run expired', "
                    "updated_at=datetime('now') "
                    "WHERE session_id=? AND status='running' "
                    "AND updated_at < datetime('now', ?)",
                    (session_id, f"-{int(max_age_seconds)} seconds"),
                )
            else:
                cur = c.execute(
                    "UPDATE runs SET status='failed', error_message='stale run expired', "
                    "updated_at=datetime('now') "
                    "WHERE status='running' "
                    "AND updated_at < datetime('now', ?)",
                    (f"-{int(max_age_seconds)} seconds",),
                )
            return int(cur.rowcount or 0)

    return await run_in_thread(_do)


async def create_run(session_id: str) -> str:
    await expire_stale_runs(session_id)
    run_id = _new_run_id()

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO runs(id, session_id, status) VALUES (?, ?, 'running')",
                (run_id, session_id),
            )

    await run_in_thread(_do)
    return run_id


async def create_response(
    session_id: str,
    *,
    run_id: str | None = None,
    previous_response_id: str | None = None,
    assistant_message_id: int | None = None,
    model: str | None = None,
    input_text: str = "",
    output_text: str = "",
    status: str = "completed",
) -> str:
    response_id = _new_response_id()

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO responses("
                "id, session_id, run_id, previous_response_id, assistant_message_id, "
                "model, input_text, output_text, status"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    response_id,
                    session_id,
                    run_id,
                    previous_response_id,
                    assistant_message_id,
                    model,
                    input_text,
                    output_text,
                    status,
                ),
            )

    await run_in_thread(_do)
    return response_id


async def get_response(response_id: str) -> dict[str, Any] | None:
    def _do() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id, session_id, run_id, previous_response_id, assistant_message_id, "
                "model, input_text, output_text, status, created_at, updated_at "
                "FROM responses WHERE id = ?",
                (response_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    return await run_in_thread(_do)


async def get_response_session_id(response_id: str) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT session_id FROM responses WHERE id = ?",
                (response_id,),
            ).fetchone()
            return str(row["session_id"]) if row else None

    return await run_in_thread(_do)


async def update_run(
    run_id: str,
    *,
    status: str | None = None,
    assistant_message_id: int | None = None,
    error_message: str | None = None,
) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            updates = ["updated_at = datetime('now')"]
            params: list[Any] = []
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if assistant_message_id is not None:
                updates.append("assistant_message_id = ?")
                params.append(assistant_message_id)
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            params.append(run_id)
            c.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id = ?", params)

    await run_in_thread(_do)


async def get_active_run(session_id: str) -> dict[str, Any] | None:
    await expire_stale_runs(session_id)

    def _do() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id, session_id, status, assistant_message_id, error_message, "
                "created_at, updated_at FROM runs "
                "WHERE session_id = ? AND status = 'running' "
                "ORDER BY updated_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            d = dict(row)
            msg_id = d.get("assistant_message_id")
            if msg_id:
                msg = c.execute(
                    "SELECT id, role, content, tool_calls, tool_call_id, created_at "
                    "FROM messages WHERE id = ?",
                    (msg_id,),
                ).fetchone()
                if msg is not None:
                    md = dict(msg)
                    if md.get("tool_calls"):
                        try:
                            md["tool_calls"] = json.loads(md["tool_calls"])
                        except json.JSONDecodeError:
                            md["tool_calls"] = None
                    d["assistant_message"] = md
            return d

    run = await run_in_thread(_do)
    if run is None:
        return None
    return run


async def append_message(
    session_id: str,
    role: str,
    content: str,
    *,
    tool_calls: Any = None,
    tool_call_id: str | None = None,
    run_id: str | None = None,
    tokens: int | None = None,
) -> int:
    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            cur = c.execute(
                "INSERT INTO messages(session_id, role, content, tool_calls, tool_call_id, run_id, tokens) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    role,
                    content,
                    json.dumps(tool_calls) if tool_calls else None,
                    tool_call_id,
                    run_id,
                    tokens,
                ),
            )
            return int(cur.lastrowid or 0)

    return await run_in_thread(_do)


async def update_message(
    message_id: int,
    *,
    content: str | None = None,
    tool_calls: Any = None,
    tokens: int | None = None,
) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            updates: list[str] = []
            params: list[Any] = []
            if content is not None:
                updates.append("content = ?")
                params.append(content)
            if tool_calls is not None:
                updates.append("tool_calls = ?")
                params.append(json.dumps(tool_calls) if tool_calls else None)
            if tokens is not None:
                updates.append("tokens = ?")
                params.append(tokens)
            if not updates:
                return False
            params.append(message_id)
            sql = f"UPDATE messages SET {', '.join(updates)} WHERE id = ?"
            cur = c.execute(sql, params)
            return (cur.rowcount or 0) > 0

    return await run_in_thread(_do)


async def persist_openai_message(
    session_id: str,
    msg: dict[str, Any],
    *,
    run_id: str | None = None,
) -> int:
    role = msg.get("role")
    if role == "assistant":
        return await append_message(
            session_id,
            "assistant",
            str(msg.get("content") or ""),
            tool_calls=msg.get("tool_calls"),
            run_id=run_id,
        )
    if role == "tool":
        return await append_message(
            session_id,
            "tool",
            str(msg.get("content") or ""),
            tool_call_id=str(msg.get("tool_call_id") or ""),
            run_id=run_id,
        )
    if role == "user":
        return await append_message(session_id, "user", str(msg.get("content") or ""), run_id=run_id)
    raise ValueError(f"unsupported role for persist: {role}")


async def build_llm_messages(session_id: str) -> list[dict[str, Any]]:
    """从 DB 重建 OpenAI 格式上下文（跳过 legacy UI 伪 tool 消息）。"""

    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT role, content, tool_calls, tool_call_id "
                "FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()

        out: list[dict[str, Any]] = []
        for r in rows:
            role = r["role"]
            content = r["content"] or ""
            tool_calls_raw = r["tool_calls"]
            tool_calls = None
            if tool_calls_raw:
                try:
                    tool_calls = json.loads(tool_calls_raw)
                except json.JSONDecodeError:
                    tool_calls = None

            if role == "user":
                out.append({"role": "user", "content": content})
                continue

            if role == "assistant":
                if _is_legacy_event_meta(tool_calls):
                    continue
                d: dict[str, Any] = {"role": "assistant"}
                if content:
                    d["content"] = content
                if _is_openai_tool_calls(tool_calls):
                    d["tool_calls"] = tool_calls
                if d.get("content") is not None or d.get("tool_calls"):
                    out.append(d)
                continue

            if role == "tool":
                if _is_legacy_event_meta(tool_calls):
                    if tool_calls and tool_calls[0].get("event_type") == "tool_result":
                        tc_id = tool_calls[0].get("tool_call_id") or ""
                        preview = tool_calls[0].get("preview") or content
                        if tc_id:
                            out.append({"role": "tool", "tool_call_id": tc_id, "content": preview})
                    continue
                tc_id = r["tool_call_id"] or ""
                if tc_id:
                    out.append({"role": "tool", "tool_call_id": tc_id, "content": content})
        return out

    return await run_in_thread(_do)


async def get_last_user_message(session_id: str) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
                "ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            return str(row["content"]) if row else None

    return await run_in_thread(_do)


async def list_sessions(limit: int = 50) -> list[dict]:
    def _do() -> list[dict]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, title, status, total_tokens, created_at, updated_at "
                "FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def get_session_title(session_id: str) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute("SELECT title FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            title = row["title"]
            return str(title) if title is not None else None

    return await run_in_thread(_do)


async def list_messages(session_id: str) -> list[dict]:
    def _do() -> list[dict]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, role, content, tool_calls, tool_call_id, run_id, tokens, created_at "
                "FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                d = dict(r)
                if d.get("tool_calls"):
                    try:
                        d["tool_calls"] = json.loads(d["tool_calls"])
                    except json.JSONDecodeError:
                        d["tool_calls"] = None
                out.append(d)
            return out

    return await run_in_thread(_do)


async def delete_session(session_id: str) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            c.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cur = c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return (cur.rowcount or 0) > 0

    return await run_in_thread(_do)
