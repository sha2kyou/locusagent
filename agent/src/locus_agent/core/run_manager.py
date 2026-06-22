"""后台 Chat Run：loop 与 SSE 解耦，客户端断连不中断生成。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..logging import get_logger
from ..tools import ToolRegistry
from .loop import run_chat_loop_stream
from .stream_health import StreamHealthError
from .persistence import (
    append_message,
    expire_stale_run_ids,
    get_active_run,
    link_message_attachments,
    update_message,
    update_run,
    upsert_session_meta,
)
from ..memory.queue import bump_message_embedding
from .post_run import schedule_post_run

log = get_logger("run_manager")

FINISHED = "_finished"
ERROR = "_error"
CANCELLED_MARK = "run cancelled by user"
HEARTBEAT_SECONDS = 60

_active: dict[str, StreamRunHandle] = {}


def _try_enqueue_sse(handle: StreamRunHandle, ev: dict[str, Any]) -> None:
    """向所有 SSE 订阅者投递事件；队列满时丢弃，避免 worker 被慢客户端拖死。"""
    for queue in list(handle.subscribers):
        try:
            queue.put_nowait(ev)
        except asyncio.QueueFull:
            log.warning(
                "sse_queue_full",
                run_id=handle.run_id,
                session_id=handle.session_id,
                event_type=ev.get("type"),
            )


async def _emit_loop_event(
    handle: StreamRunHandle,
    persist_queue: asyncio.Queue[dict[str, Any] | None],
    public: dict[str, Any],
) -> None:
    await persist_queue.put(public)
    _try_enqueue_sse(handle, public)


@dataclass
class StreamRunHandle:
    run_id: str
    session_id: str
    subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)
    task: asyncio.Task[None] = field(init=False, repr=False)


def attach_run_subscriber(handle: StreamRunHandle) -> asyncio.Queue[dict[str, Any]]:
    """为 SSE 客户端注册独立队列，仅接收订阅后的新事件。"""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
    handle.subscribers.append(queue)
    return queue


def detach_run_subscriber(handle: StreamRunHandle, queue: asyncio.Queue[dict[str, Any]]) -> None:
    try:
        handle.subscribers.remove(queue)
    except ValueError:
        pass


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
    if ev.get("ephemeral"):
        return
    t = ev["type"]
    if t in ("delta", "reasoning_delta"):
        piece = str(ev.get("content") or "")
        if not piece:
            return
        if state.get("after_tool_round"):
            state["assistant_msg_id"] = None
            state["partial_text"] = ""
            state["partial_reasoning"] = ""
            state["after_tool_round"] = False
        if t == "reasoning_delta":
            state["partial_reasoning"] = str(state.get("partial_reasoning") or "") + piece
        else:
            state["partial_text"] = str(state.get("partial_text") or "") + piece
        content = str(state.get("partial_text") or "")
        reasoning = str(state.get("partial_reasoning") or "")
        assistant_msg_id = state.get("assistant_msg_id")
        if assistant_msg_id is None:
            mid = await append_message(
                session_id,
                "assistant",
                content,
                reasoning_content=reasoning,
                run_id=run_id,
                enqueue_embedding=False,
            )
            state["assistant_msg_id"] = mid
            await update_run(run_id, assistant_message_id=mid)
        else:
            await update_message(
                assistant_msg_id,
                content=content,
                reasoning_content=reasoning,
                reindex_embedding=False,
            )
        await update_run(run_id)
        return

    if t == "assistant_tools":
        tool_msg = ev.get("message") or {}
        assistant_msg_id = state.get("assistant_msg_id")
        partial = str(state.get("partial_text") or "")
        partial_reasoning = str(state.get("partial_reasoning") or "")
        already_after_tool_round = bool(state.get("after_tool_round"))
        # 同一轮里：已有(可能含流式文本的)assistant 消息时就地补 tool_calls，
        # 合并成规范的单条 assistant(content + tool_calls)，避免拆成两条
        can_update_in_place = assistant_msg_id is not None and not already_after_tool_round
        if can_update_in_place:
            await update_message(
                assistant_msg_id,
                content=str(tool_msg.get("content") or partial),
                reasoning_content=str(tool_msg.get("reasoning_content") or partial_reasoning),
                tool_calls=tool_msg.get("tool_calls"),
                reindex_embedding=False,
            )
        else:
            mid = await append_message(
                session_id,
                "assistant",
                str(tool_msg.get("content") or ""),
                reasoning_content=str(tool_msg.get("reasoning_content") or partial_reasoning),
                tool_calls=tool_msg.get("tool_calls"),
                run_id=run_id,
                enqueue_embedding=False,
            )
            state["assistant_msg_id"] = mid
            await update_run(run_id, assistant_message_id=mid)
        state["partial_text"] = ""
        state["partial_reasoning"] = ""
        state["after_tool_round"] = True
        return

    if t == "tool_result":
        preview = str(ev.get("preview") or "")
        full_content = str(ev.get("content") or preview)
        tool_call_id = str(ev.get("tool_call_id") or "")
        tool_name = str(ev.get("name") or "")
        tool_kind = str(ev.get("tool_kind") or _tool_kind(tool_name))
        elapsed_ms = ev.get("elapsed_ms")
        tool_meta = [
            {
                "event_type": "tool_result",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_kind": tool_kind,
                "preview": preview,
                **(
                    {"elapsed_ms": int(elapsed_ms)}
                    if elapsed_ms is not None and int(elapsed_ms) >= 0
                    else {}
                ),
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

    if t == "attachment":
        att_id = str(ev.get("id") or "")
        assistant_msg_id = state.get("assistant_msg_id")
        if assistant_msg_id and att_id:
            await link_message_attachments(int(assistant_msg_id), [att_id])
        return

    if t == "done":
        state["final_text"] = ev.get("final_text") or ""
        state["final_reasoning"] = ev.get("final_reasoning") or ""
        state["total_tokens"] = int(ev.get("total_tokens") or 0)
        state["tool_calls_made"] = int(ev.get("tool_calls_made") or 0)
        state["loop_rounds"] = int(ev.get("rounds") or 0)
        final_text = str(state.get("final_text") or "")
        if final_text and not str(state.get("partial_text") or "").strip():
            state["partial_text"] = final_text
            state["partial_reasoning"] = str(state.get("final_reasoning") or "")
            assistant_msg_id = state.get("assistant_msg_id")
            if assistant_msg_id is None:
                mid = await append_message(
                    session_id,
                    "assistant",
                    final_text,
                    reasoning_content=str(state.get("partial_reasoning") or ""),
                    run_id=run_id,
                    enqueue_embedding=False,
                )
                state["assistant_msg_id"] = mid
                await update_run(run_id, assistant_message_id=mid)
            else:
                await update_message(
                    assistant_msg_id,
                    content=final_text,
                    reasoning_content=str(state.get("partial_reasoning") or ""),
                    reindex_embedding=False,
                )
            await update_run(run_id)


async def _finalize_run(session_id: str, run_id: str, state: dict[str, Any], *, error: str | None) -> None:
    assistant_msg_id = state.get("assistant_msg_id")
    final_text = str(state.get("final_text") or "")
    final_reasoning = str(state.get("final_reasoning") or "")
    partial_text = str(state.get("partial_text") or "")
    partial_reasoning = str(state.get("partial_reasoning") or "")
    content = final_text or partial_text
    reasoning = final_reasoning or partial_reasoning
    total_tokens = int(state.get("total_tokens") or 0)
    try:
        if error:
            status = "cancelled" if error == CANCELLED_MARK else "failed"
            await update_run(run_id, status=status, error_message=error)
            from .persistence import reconcile_incomplete_tool_rounds

            await reconcile_incomplete_tool_rounds(session_id)
            return
        if assistant_msg_id is None:
            assistant_msg_id = await append_message(
                session_id,
                "assistant",
                content,
                reasoning_content=reasoning,
                tokens=total_tokens,
                run_id=run_id,
            )
        else:
            await update_message(
                assistant_msg_id,
                content=content,
                reasoning_content=reasoning,
                tokens=total_tokens,
                reindex_embedding=False,
            )
            if str(content or "").strip() or str(reasoning or "").strip():
                asyncio.create_task(
                    bump_message_embedding(int(assistant_msg_id)),
                    name=f"embed-msg-{assistant_msg_id}",
                )
        await update_run(
            run_id,
            status="completed",
            assistant_message_id=assistant_msg_id,
        )
        await upsert_session_meta(session_id, tokens_delta=total_tokens)
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
) -> None:
    call_name_by_id: dict[str, str] = {}
    state: dict[str, Any] = {
        "partial_text": "",
        "assistant_msg_id": None,
        "after_tool_round": False,
        "final_text": "",
        "total_tokens": 0,
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
    persist_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _persist_drainer() -> None:
        while True:
            ev = await persist_queue.get()
            if ev is None:
                persist_queue.task_done()
                break
            try:
                await _persist_event(handle.session_id, handle.run_id, ev, state)
            except Exception as exc:
                log.warning(
                    "run_persist_event_failed",
                    run_id=handle.run_id,
                    session_id=handle.session_id,
                    event_type=ev.get("type"),
                    error=str(exc),
                )
            finally:
                persist_queue.task_done()

    persist_task = asyncio.create_task(_persist_drainer(), name=f"run-persist-{handle.run_id}")
    try:
        async for ev in run_chat_loop_stream(
            messages,
            registry=registry,
            model=model,
            extra=extra,
            session_id=handle.session_id,
            run_id=handle.run_id,
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
            await _emit_loop_event(handle, persist_queue, public)
    except asyncio.CancelledError:
        stream_error = CANCELLED_MARK
        log.info("run_worker_cancelled", run_id=handle.run_id, session_id=handle.session_id)
        _try_enqueue_sse(handle, {"type": ERROR, "message": "已停止生成"})
    except StreamHealthError as exc:
        stream_error = str(exc)
        log.warning(
            "run_stream_health_abort",
            run_id=handle.run_id,
            code=exc.code,
            error=stream_error,
        )
        _try_enqueue_sse(
            handle,
            {"type": ERROR, "message": stream_error, "code": exc.code},
        )
    except Exception as exc:
        stream_error = str(exc)
        log.error("run_worker_failed", run_id=handle.run_id, error=stream_error)
        _try_enqueue_sse(handle, {"type": ERROR, "message": stream_error})
    else:
        _try_enqueue_sse(
            handle,
            {
                "type": FINISHED,
                "final_text": state.get("final_text") or "",
                "total_tokens": state.get("total_tokens") or 0,
                "error": stream_error,
            },
        )
    stop_heartbeat.set()
    heartbeat_task.cancel()
    await persist_queue.put(None)
    await persist_task
    await _finalize_run(handle.session_id, handle.run_id, state, error=stream_error)
    _active.pop(handle.run_id, None)

    if stream_error is None:
        schedule_post_run(
            session_id=handle.session_id,
            loop_rounds=int(state.get("loop_rounds") or 0),
            model=str(state.get("model") or "") or None,
        )


def start_stream_run(
    *,
    run_id: str,
    session_id: str,
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    model: str,
    extra: dict[str, Any] | None,
) -> tuple[StreamRunHandle, asyncio.Queue[dict[str, Any]]]:
    handle = StreamRunHandle(run_id=run_id, session_id=session_id)
    queue = attach_run_subscriber(handle)
    handle.task = asyncio.create_task(
        _worker(
            handle,
            messages=messages,
            registry=registry,
            model=model,
            extra=extra,
        ),
        name=f"chat-run-{run_id}",
    )
    _active[run_id] = handle
    return handle, queue


def get_run_handle(run_id: str) -> StreamRunHandle | None:
    return _active.get(run_id)


async def reconcile_session_active_handles(session_id: str) -> int:
    """对齐内存活跃任务与 DB 活跃 run，取消多余/陈旧 worker。"""
    stale_ids = await expire_stale_run_ids(session_id)
    active_run = await get_active_run(session_id)
    keep_run_id = str(active_run.get("id") or "") if active_run else ""
    cancelled = 0
    stale_set = set(stale_ids)
    for handle in list(_active.values()):
        if handle.session_id != session_id:
            continue
        if keep_run_id and handle.run_id == keep_run_id and handle.run_id not in stale_set:
            continue
        if not handle.task.done():
            handle.task.cancel()
            cancelled += 1
    return cancelled


async def shutdown_run_manager(*, timeout_seconds: float = 3.0) -> None:
    """在应用关闭时取消活跃 run 与 post-run 任务并等待收敛。"""
    active_handles = list(_active.values())
    for handle in active_handles:
        if not handle.task.done():
            handle.task.cancel()
    if active_handles:
        try:
            await asyncio.wait_for(
                asyncio.gather(*(h.task for h in active_handles), return_exceptions=True),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            pass
    _active.clear()

    from .post_run import shutdown_post_run_worker

    await shutdown_post_run_worker(timeout_seconds=timeout_seconds)


async def cancel_active_run(session_id: str) -> bool:
    """取消会话当前运行中的 run。"""
    await reconcile_session_active_handles(session_id)
    run = await get_active_run(session_id)
    if not run:
        return False
    run_id = str(run.get("id") or "")
    if not run_id:
        return False
    handle = _active.get(run_id)
    if handle and not handle.task.done():
        handle.task.cancel()
    # 立即写入终态，避免 worker 收尾前 get_active_run 仍返回 running
    await update_run(run_id, status="cancelled", error_message=CANCELLED_MARK)
    _active.pop(run_id, None)
    return True
