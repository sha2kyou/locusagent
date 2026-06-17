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
from ..core.post_run import schedule_post_run
from ..core.system_prompt import get_or_create_system_prompt
from ..host_settings import build_runtime_time_context
from ..logging import get_logger

log = get_logger("scheduled_run")

_TITLE_MAX = 28
_NON_INTERACTIVE_SYSTEM_PROMPT = (
    "## Scheduled Run Mode\n"
    "- This run is triggered automatically by system scheduler.\n"
    "- No user is present to answer follow-up questions.\n"
    "- Never call clarify; make a reasonable default decision and continue.\n"
    "- If requirements are not fully specified, proceed with the smallest sensible output.\n"
    "- Do NOT ask the user to switch to interactive mode or wait for confirmation.\n"
    "- memory tool (add/replace/remove) IS available in scheduled runs. "
    "When the prompt asks for memory maintenance, consolidation, or cleanup, "
    "execute it directly via memory tool calls—do not defer to a later interactive session.\n"
    "- The memory snapshot in the volatile system prompt layer is a read cache; "
    "it does not block memory writes during this run.\n"
)
_SCHEDULED_DISABLED_TOOLS = {
    "clarify",
    "scheduled_task_manage",
    "skill_manage",
    "hook_manage",
    "artifact_delete",
    "artifact_update",
    "artifact_category_update",
    "artifact_category_delete",
    "delete_file",
    "session_delete",
    "notification_mark_read",
    "mcp_manage",
    "mcp_refresh",
    "todo",
}
_SCHEDULED_BLOCKED_TOOL_ACTIONS = {
    "env_vars": {"add", "update", "delete"},
}


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


async def run_scheduled_prompt(*, title: str, prompt: str, task_id: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    from .models import resolve_model

    model = await resolve_model("main")
    session_title = (title or "").strip()[:_TITLE_MAX] or "定时任务"
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    sid = await create_session(title=session_title, hidden=True)
    if task_id is not None:
        from ..host_scheduled_tasks import notify_scheduled_run_started

        await notify_scheduled_run_started(task_id, sid)
    run_id: str | None = None
    lock = await session_lock(sid)
    async with lock:
        try:
            run_id = await create_run(sid)
            user_mid = await append_message(sid, "user", prompt)
            from .session_review_state import begin_user_turn
            from ..hooks import emit_post_user_submit
            from ..workspace import get_workspace_id

            await begin_user_turn(sid)
            await emit_post_user_submit(
                session_id=sid,
                user_message=prompt,
                user_message_id=user_mid if user_mid > 0 else None,
                submit_source="scheduled",
                workspace_id=get_workspace_id(),
            )
            system_prompt = await get_or_create_system_prompt(sid)
            db_msgs = await build_llm_messages(sid)
            messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            messages.append({"role": "system", "content": _NON_INTERACTIVE_SYSTEM_PROMPT})
            messages.append({"role": "system", "content": await build_runtime_time_context()})
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
                disabled_tools=_SCHEDULED_DISABLED_TOOLS,
                blocked_tool_actions=_SCHEDULED_BLOCKED_TOOL_ACTIONS,
                usage_scenario="scheduled_run",
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

            schedule_post_run(
                session_id=sid,
                loop_rounds=result.rounds,
                model=model,
                messages=final_messages,
            )

            payload = {
                "ok": True,
                "session_id": sid,
                "run_id": run_id,
                "final_text": result.final_text,
            }
            if task_id is not None:
                from ..host_scheduled_tasks import notify_scheduled_run_finished

                await notify_scheduled_run_finished(
                    task_id,
                    ok=True,
                    session_id=sid,
                    final_text=result.final_text,
                )
            return payload
        except Exception as exc:
            await _mark_run_failed(run_id, exc)
            if task_id is not None:
                from ..host_scheduled_tasks import notify_scheduled_run_finished

                await notify_scheduled_run_finished(
                    task_id,
                    ok=False,
                    session_id=sid,
                    error=str(exc),
                )
            raise ScheduledRunError(str(exc), session_id=sid, run_id=run_id) from exc
