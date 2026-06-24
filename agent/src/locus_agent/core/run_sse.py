"""将 run 事件编码为 OpenAI 兼容 SSE chunk。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from ..logging import get_logger
from .run_manager import ERROR, FINISHED

log = get_logger("run_sse")


def tool_kind(name: str | None) -> str:
    n = (name or "").lower()
    if n.startswith("skill_") or "skill" in n:
        return "skill"
    if n.startswith("mcp_") or "mcp" in n:
        return "mcp"
    if "memory" in n:
        return "memory"
    return "tool"


def sse_chunk(
    *,
    chat_id: str,
    public_model: str,
    created: int,
    delta: dict[str, Any],
    session_id: str,
    run_id: str,
    **extra_fields: Any,
) -> str:
    body: dict[str, Any] = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": public_model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        "session_id": session_id,
        "run_id": run_id,
    }
    body.update(extra_fields)
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def drain_subscriber_queue_nowait(queue: asyncio.Queue[dict[str, Any]]) -> list[dict[str, Any]]:
    drained: list[dict[str, Any]] = []
    while True:
        try:
            drained.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return drained


def build_resume_sync_payload(
    run: dict[str, Any] | None,
    pending: list[dict[str, Any]],
) -> dict[str, Any]:
    """合并 DB 快照与订阅瞬间已入队的文本增量，避免重连时丢字或重复。"""
    am = (run or {}).get("assistant_message") or {}
    text = str(am.get("content") or "")
    reasoning = str(am.get("reasoning_content") or "")
    for ev in pending:
        t = ev.get("type")
        if t == "delta":
            text += str(ev.get("content") or "")
        elif t == "reasoning_delta":
            reasoning += str(ev.get("reasoning_content") or "")
    replay: list[dict[str, Any]] = []
    for ev in pending:
        t = ev.get("type")
        if t in ("delta", "reasoning_delta", FINISHED, ERROR):
            continue
        replay.append(ev)
    return {
        "assistant_message_id": am.get("id"),
        "content": text,
        "reasoning_content": reasoning,
        "replay": replay,
    }


def _encode_loop_event(
    ev: dict[str, Any],
    *,
    chat_id: str,
    public_model: str,
    created: int,
    session_id: str,
    run_id: str,
) -> str | None:
    t = ev.get("type")
    if t == ERROR:
        return sse_chunk(
            delta={},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
            x_event="error",
            x_message=ev.get("message") or "unknown",
        )
    if t == "reasoning_delta":
        return sse_chunk(
            delta={"reasoning_content": ev.get("content") or ""},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
        )
    if t == "delta":
        return sse_chunk(
            delta={"content": ev.get("content") or ""},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
        )
    if t == "tool_call":
        tool_name = str(ev.get("name") or "")
        kind = ev.get("tool_kind") or tool_kind(tool_name)
        return sse_chunk(
            delta={},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
            x_event="tool_call",
            x_tool_name=tool_name,
            x_tool_kind=kind,
            x_tool_id=ev.get("id"),
            x_tool_args=ev.get("arguments"),
            x_tool_started_at=ev.get("started_at"),
        )
    if t == "tool_result":
        return sse_chunk(
            delta={},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
            x_event="tool_result",
            x_tool_call_id=ev.get("tool_call_id"),
            x_tool_name=ev.get("name"),
            x_preview=ev.get("preview"),
            x_elapsed_ms=ev.get("elapsed_ms"),
        )
    if t == "attachment":
        return sse_chunk(
            delta={},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
            x_event="attachment",
            x_attachment_id=ev.get("id"),
            x_attachment_name=ev.get("name"),
        )
    if t == "terminal_approval":
        return sse_chunk(
            delta={},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
            x_event="terminal_approval",
            x_approval_id=ev.get("approval_id"),
            x_terminal_command=ev.get("command"),
            x_terminal_head=ev.get("head"),
            x_tool_call_id=ev.get("tool_call_id"),
            x_approval_timeout=ev.get("timeout_seconds"),
            x_approval_expires_at=ev.get("expires_at"),
        )
    return None


async def iter_run_sse(
    queue: asyncio.Queue[dict[str, Any]],
    *,
    chat_id: str,
    public_model: str,
    created: int,
    session_id: str,
    run_id: str,
    resume_sync: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    if resume_sync:
        yield sse_chunk(
            delta={},
            chat_id=chat_id,
            public_model=public_model,
            created=created,
            session_id=session_id,
            run_id=run_id,
            x_event="sync",
            x_sync=resume_sync,
        )
    yield sse_chunk(
        delta={"role": "assistant"},
        chat_id=chat_id,
        public_model=public_model,
        created=created,
        session_id=session_id,
        run_id=run_id,
    )
    try:
        for ev in resume_sync.get("replay", []) if resume_sync else []:
            encoded = _encode_loop_event(
                ev,
                chat_id=chat_id,
                public_model=public_model,
                created=created,
                session_id=session_id,
                run_id=run_id,
            )
            if encoded:
                yield encoded
        while True:
            ev = await queue.get()
            t = ev.get("type")
            if t == FINISHED:
                break
            if t == ERROR:
                encoded = _encode_loop_event(
                    ev,
                    chat_id=chat_id,
                    public_model=public_model,
                    created=created,
                    session_id=session_id,
                    run_id=run_id,
                )
                if encoded:
                    yield encoded
                break
            encoded = _encode_loop_event(
                ev,
                chat_id=chat_id,
                public_model=public_model,
                created=created,
                session_id=session_id,
                run_id=run_id,
            )
            if encoded:
                yield encoded
    except asyncio.CancelledError:
        log.info("run_sse_disconnected", run_id=run_id, session_id=session_id)
        raise

    done = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": public_model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "run_id": run_id,
        "session_id": session_id,
    }
    yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
