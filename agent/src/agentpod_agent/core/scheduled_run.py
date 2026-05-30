"""定时任务：新建会话并跑一轮非流式对话。"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..core.loop import run_chat_loop
from ..core.persistence import (
    append_message,
    build_llm_messages,
    create_run,
    create_session,
    persist_openai_message,
    session_lock,
    update_run,
    upsert_session_meta,
)
from ..core.post_run import run_post_tasks
from ..core.system_prompt import get_or_create_system_prompt
from ..logging import get_logger

log = get_logger("scheduled_run")

_TITLE_MAX = 28


class ScheduledRunError(Exception):
    def __init__(self, message: str, *, session_id: str, run_id: str | None = None) -> None:
        super().__init__(message)
        self.session_id = session_id
        self.run_id = run_id


async def _persist_loop_messages(
    sid: str,
    final_messages: list[dict[str, Any]],
    initial_len: int,
    *,
    run_id: str,
) -> int | None:
    last_assistant_id: int | None = None
    for msg in final_messages[initial_len:]:
        role = msg.get("role")
        if role not in ("assistant", "tool"):
            continue
        mid = await persist_openai_message(sid, msg, run_id=run_id)
        if role == "assistant":
            last_assistant_id = mid
    return last_assistant_id


async def _mark_run_failed(run_id: str | None, exc: Exception) -> None:
    if not run_id:
        return
    try:
        await update_run(run_id, status="failed", error_message=str(exc))
    except Exception as mark_exc:
        log.warning("scheduled_run_mark_failed", error=str(mark_exc))


async def run_scheduled_prompt(*, title: str, prompt: str) -> dict[str, Any]:
    settings = get_settings()
    model = settings.llm_model
    session_title = (title or "").strip()[:_TITLE_MAX] or "定时任务"
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    sid = await create_session(title=session_title)
    run_id: str | None = None
    lock = await session_lock(sid)
    async with lock:
        try:
            run_id = await create_run(sid)
            await append_message(sid, "user", prompt)
            system_prompt = await get_or_create_system_prompt(sid)
            db_msgs = await build_llm_messages(sid)
            messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            messages.extend(db_msgs)
            initial_len = len(messages)

            from ..tools import registry

            result, final_messages = await run_chat_loop(
                messages,
                registry=registry,
                model=model,
                extra=None,
                session_id=sid,
                run_id=run_id,
            )
            last_assistant_id = await _persist_loop_messages(
                sid, final_messages, initial_len, run_id=run_id
            )
            await update_run(
                run_id,
                status="completed",
                assistant_message_id=last_assistant_id,
            )
            await upsert_session_meta(sid, tokens_delta=result.total_tokens)

            try:
                await run_post_tasks(
                    session_id=sid,
                    tool_calls_made=result.tool_calls_made,
                    model=model,
                    messages=final_messages,
                )
            except Exception as exc:
                log.warning("scheduled_post_run_failed", error=str(exc))

            return {
                "ok": True,
                "session_id": sid,
                "run_id": run_id,
                "final_text": result.final_text,
            }
        except Exception as exc:
            await _mark_run_failed(run_id, exc)
            raise ScheduledRunError(str(exc), session_id=sid, run_id=run_id) from exc
