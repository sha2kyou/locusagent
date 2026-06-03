"""任务完成后的后台增强：Background Self-Improvement Review + 记忆策展。

均为后台任务，失败安全（仅记录日志，不影响主响应）。
"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger
from .background_review import run_background_review, should_run_background_review
from .persistence import build_llm_messages

log = get_logger("post_run")


async def run_post_tasks(
    *,
    session_id: str,
    tool_calls_made: int,
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    try:
        trajectory = messages if messages is not None else await build_llm_messages(session_id)
        if trajectory and should_run_background_review(
            tool_calls_made=tool_calls_made,
            messages=trajectory,
        ):
            await run_background_review(
                trajectory,
                review_memory=True,
                review_skills=True,
                model=model,
                session_id=session_id,
            )
    except Exception as exc:
        log.warning("post_run_background_review_failed", error=str(exc))

    try:
        from ..memory import maybe_curate_memories

        await maybe_curate_memories(model=model)
    except Exception as exc:
        log.warning("post_run_curate_failed", error=str(exc))
