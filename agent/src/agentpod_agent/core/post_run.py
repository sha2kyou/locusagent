"""任务完成后的后台增强：技能反思沉淀 + 记忆策展。

均为后台任务，失败安全（仅记录日志，不影响主响应）。
采用函数内惰性导入，避免与 core 包的导入环。
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..logging import get_logger

log = get_logger("post_run")


async def run_post_tasks(
    *,
    session_id: str,
    tool_calls_made: int,
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    settings = get_settings()

    if tool_calls_made >= settings.skill_reflect_min_tool_calls:
        try:
            from .persistence import build_llm_messages
            from ..skills.reflect import maybe_distill_skill

            trajectory = messages if messages is not None else await build_llm_messages(session_id)
            if trajectory:
                await maybe_distill_skill(trajectory, model=model)
        except Exception as exc:
            log.warning("post_run_reflect_failed", error=str(exc))

    try:
        from ..memory import maybe_curate_memories

        await maybe_curate_memories(model=model)
    except Exception as exc:
        log.warning("post_run_curate_failed", error=str(exc))
