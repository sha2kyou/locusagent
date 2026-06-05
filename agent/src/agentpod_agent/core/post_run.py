"""任务完成后的后台增强：Background Self-Improvement Review + 记忆策展。

均为后台任务，失败安全（仅记录日志，不影响主响应）。
"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger
from .background_review import assess_background_review_triggers, run_background_review
from .persistence import build_llm_messages

log = get_logger("post_run")


async def run_post_tasks(
    *,
    session_id: str,
    loop_rounds: int = 0,
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    trajectory = messages if messages is not None else await build_llm_messages(session_id)

    try:
        from .session_title import finalize_session_title

        await finalize_session_title(session_id, messages=trajectory)
    except Exception as exc:
        log.warning("post_run_session_title_failed", error=str(exc))

    try:
        if trajectory:
            review_memory, review_skills = await assess_background_review_triggers(
                session_id=session_id,
                loop_rounds=loop_rounds,
            )
            if review_memory or review_skills:
                await run_background_review(
                    trajectory,
                    review_memory=review_memory,
                    review_skills=review_skills,
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
