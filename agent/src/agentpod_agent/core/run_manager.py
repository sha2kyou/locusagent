"""后台 Chat Run：loop 与 SSE 解耦，客户端断连不中断生成。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..logging import get_logger
from ..tools import ToolRegistry
from .loop import run_chat_loop_stream
from .persistence import (
    append_message,
    get_active_run,
    update_message,
    update_run,
    upsert_session_meta,
)
from .post_run import run_post_tasks
from .session_title import maybe_generate_and_update_session_title

log = get_logger("run_manager")

FINISHED = "_finished"
ERROR = "_error"
CANCELLED_MARK = "run cancelled by user"
HEARTBEAT_SECONDS = 60

_active: dict[str, StreamRunHandle] = {}
_post_tasks: set[asyncio.Task] = set()


@dataclass
class StreamRunHandle:
    run_id: str
    session_id: str
    queue: asyncio.Queue[dict[str, Any]]
    task: asyncio.Task[None] = field(init=False, repr=False)


def _tool_kind(name: str | None) -> str:
    n = (name or "").lower()
    if n.startswith("skill_") or "skill" in n:
        return "skill"
    if n.startswith("mcp_") or "mcp" in n:
        return "mcp"
    if "memory" in n:
        return "memory"
    return "tool"


async def _persist_event(
    session_id: str,
    run_id: str,
    ev: dict[str, Any],
    state: dict[str, Any],
) -> None:
    t = ev["type"]
    if t == "delta":
        delta = str(ev.get("content") or "")
        if not delta:
            return
        if state.get("after_tool_round"):
            state["assistant_msg_id"] = None
            state["partial_text"] = ""
            state["after_tool_round"] = False
        state["partial_text"] = str(state.get("partial_text") or "") + delta
        assistant_msg_id = state.get("assistant_msg_id")
        if assistant_msg_id is None:
            mid = await append_message(
                session_id,
                "assistant",
                state["partial_text"],
                run_id=run_id,
            )
            state["assistant_msg_id"] = mid
            await update_run(run_id, assistant_message_id=mid)
        else:
            await update_message(assistant_msg_id, content=state["partial_text"])
        await update_run(run_id)
        return

    if t == "assistant_tools":
        tool_msg = ev.get("message") or {}
        assistant_msg_id = state.get("assistant_msg_id")
        partial = str(state.get("partial_text") or "")
        already_after_tool_round = bool(state.get("after_tool_round"))
        # 同一轮里：已有(可能含流式文本的)assistant 消息时就地补 tool_calls，
        # 合并成规范的单条 assistant(content + tool_calls)，避免拆成两条
        can_update_in_place = assistant_msg_id is not None and not already_after_tool_round
        if can_update_in_place:
            await update_message(
                assistant_msg_id,
                content=str(tool_msg.get("content") or partial),
                tool_calls=tool_msg.get("tool_calls"),
            )
        else:
            mid = await append_message(
                session_id,
                "assistant",
                str(tool_msg.get("content") or ""),
                tool_calls=tool_msg.get("tool_calls"),
                run_id=run_id,
            )
            state["assistant_msg_id"] = mid
            await update_run(run_id, assistant_message_id=mid)
        state["partial_text"] = ""
        state["after_tool_round"] = True
        return

    if t == "tool_result":
        preview = str(ev.get("preview") or "")
        full_content = str(ev.get("content") or preview)
        tool_call_id = str(ev.get("tool_call_id") or "")
        tool_name = str(ev.get("name") or "")
        tool_kind = str(ev.get("tool_kind") or _tool_kind(tool_name))
        tool_meta = [
            {
                "event_type": "tool_result",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_kind": tool_kind,
                "preview": preview,
            }
        ]
        await append_message(
            session_id,
            "tool",
            full_content,
            tool_calls=tool_meta,
            tool_call_id=tool_call_id,
            run_id=run_id,
        )
        return

    if t == "done":
        state["final_text"] = ev.get("final_text") or ""
        state["total_tokens"] = int(ev.get("total_tokens") or 0)
        state["tool_calls_made"] = int(ev.get("tool_calls_made") or 0)


async def _finalize_run(session_id: str, run_id: str, state: dict[str, Any], *, error: str | None) -> None:
    assistant_msg_id = state.get("assistant_msg_id")
    final_text = str(state.get("final_text") or "")
    partial_text = str(state.get("partial_text") or "")
    total_tokens = int(state.get("total_tokens") or 0)
    try:
        if error:
            status = "cancelled" if error == CANCELLED_MARK else "failed"
            await update_run(run_id, status=status, error_message=error)
            return
        if assistant_msg_id is None:
            assistant_msg_id = await append_message(
                session_id,
                "assistant",
                final_text,
                tokens=total_tokens,
                run_id=run_id,
            )
        else:
            await update_message(
                assistant_msg_id,
                content=final_text or partial_text,
                tokens=total_tokens,
            )
        await update_run(
            run_id,
            status="completed",
            assistant_message_id=assistant_msg_id,
        )
        await upsert_session_meta(session_id, tokens_delta=total_tokens)
        auto_title_user_query = str(state.get("auto_title_user_query") or "").strip()
        if auto_title_user_query:
            await maybe_generate_and_update_session_title(
                session_id,
                user_query=auto_title_user_query,
                assistant_text=final_text or partial_text,
                model=str(state.get("model") or "") or None,
            )
    except Exception as exc:
        log.warning("run_finalize_failed", run_id=run_id, error=str(exc))
        await update_run(run_id, status="failed", error_message=str(exc))


async def _worker(
    handle: StreamRunHandle,
    *,
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    model: str,
    extra: dict[str, Any] | None,
    auto_title_user_query: str | None,
) -> None:
    call_name_by_id: dict[str, str] = {}
    state: dict[str, Any] = {
        "partial_text": "",
        "assistant_msg_id": None,
        "after_tool_round": False,
        "final_text": "",
        "total_tokens": 0,
        "auto_title_user_query": auto_title_user_query or "",
        "model": model,
    }
    stream_error: str | None = None

    # 心跳：长工具调用期间无 delta 时也推进 run.updated_at，避免被 expire_stale_runs 误标
    stop_heartbeat = asyncio.Event()

    async def _heartbeat() -> None:
        while not stop_heartbeat.is_set():
            try:
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                try:
                    await update_run(handle.run_id)
                except Exception:
                    pass

    heartbeat_task = asyncio.create_task(_heartbeat(), name=f"run-heartbeat-{handle.run_id}")
    try:
        async for ev in run_chat_loop_stream(
            messages,
            registry=registry,
            model=model,
            extra=extra,
        ):
            public = dict(ev)
            et = str(public.get("type") or "")
            if et == "tool_call":
                tool_name = str(public.get("name") or "")
                tool_id = str(public.get("id") or "")
                if tool_id and tool_name:
                    call_name_by_id[tool_id] = tool_name
                public["tool_kind"] = _tool_kind(tool_name)
            elif et == "tool_result":
                tool_call_id = str(public.get("tool_call_id") or "")
                mapped_name = call_name_by_id.get(tool_call_id, "")
                if mapped_name:
                    public["name"] = mapped_name
                tool_name = str(public.get("name") or "")
                public["tool_kind"] = _tool_kind(tool_name)
            await _persist_event(handle.session_id, handle.run_id, public, state)
            await handle.queue.put(public)
    except asyncio.CancelledError:
        stream_error = CANCELLED_MARK
        log.info("run_worker_cancelled", run_id=handle.run_id, session_id=handle.session_id)
        await handle.queue.put({"type": ERROR, "message": "已停止生成"})
    except Exception as exc:
        stream_error = str(exc)
        log.error("run_worker_failed", run_id=handle.run_id, error=stream_error)
        await handle.queue.put({"type": ERROR, "message": stream_error})
    else:
        await handle.queue.put(
            {
                "type": FINISHED,
                "final_text": state.get("final_text") or "",
                "total_tokens": state.get("total_tokens") or 0,
                "error": stream_error,
            }
        )
    stop_heartbeat.set()
    heartbeat_task.cancel()
    await _finalize_run(handle.session_id, handle.run_id, state, error=stream_error)
    _active.pop(handle.run_id, None)

    if stream_error is None:
        post = asyncio.create_task(
            run_post_tasks(
                session_id=handle.session_id,
                tool_calls_made=int(state.get("tool_calls_made") or 0),
                model=str(state.get("model") or "") or None,
            ),
            name=f"post-run-{handle.run_id}",
        )
        _post_tasks.add(post)
        post.add_done_callback(_post_tasks.discard)


def start_stream_run(
    *,
    run_id: str,
    session_id: str,
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    model: str,
    extra: dict[str, Any] | None,
    auto_title_user_query: str | None = None,
) -> StreamRunHandle:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
    handle = StreamRunHandle(run_id=run_id, session_id=session_id, queue=queue)
    handle.task = asyncio.create_task(
        _worker(
            handle,
            messages=messages,
            registry=registry,
            model=model,
            extra=extra,
            auto_title_user_query=auto_title_user_query,
        ),
        name=f"chat-run-{run_id}",
    )
    _active[run_id] = handle
    return handle


def get_run_handle(run_id: str) -> StreamRunHandle | None:
    return _active.get(run_id)


async def cancel_active_run(session_id: str) -> bool:
    """取消会话当前运行中的 run。"""
    run = await get_active_run(session_id)
    if not run:
        return False
    run_id = str(run.get("id") or "")
    if not run_id:
        return False
    handle = _active.get(run_id)
    if handle and not handle.task.done():
        handle.task.cancel()
        return True
    await update_run(run_id, status="cancelled", error_message=CANCELLED_MARK)
    _active.pop(run_id, None)
    return True
