"""Skill 语义路由：对话前召回匹配 skill。"""

from __future__ import annotations

from ..config import get_settings
from ..logging import get_logger
from ..tool_settings import is_skill_enabled
from ..tools import registry as tool_registry
from .embeddings import (
    SkillMatch,
    flush_pending_skill_reindexes,
    mark_all_skills_reindex,
    match_skills,
    reindex_all_skills,
)
from .store import list_skills

log = get_logger("skill_router")


def _skill_view_available() -> bool:
    return any(t.name == "skill_view" and t.enabled for t in tool_registry.all())


async def route_skills(user_query: str) -> list[SkillMatch]:
    if not (user_query or "").strip():
        return []
    if not _skill_view_available():
        return []
    await flush_pending_skill_reindexes()
    top_k = max(1, int(get_settings().skill_route_top_k))
    matches = await match_skills(user_query, top_k=top_k)
    if not matches and list_skills():
        await reindex_all_skills()
        matches = await match_skills(user_query, top_k=top_k)
    return [m for m in matches if is_skill_enabled(m.skill_name)]


async def build_skill_route_message(user_query: str) -> str | None:
    matches = await route_skills(user_query)
    if not matches:
        return None
    lines = [
        "## Skill router",
        "Semantic pre-match for the user's latest message. "
        "Call skill_view for the matched skill(s) as your first tool call before answering; "
        "do not guess skill contents.",
    ]
    for match in matches:
        lines.append(f"- {match.skill_name} (distance {match.score:.3f}, chunk {match.chunk_id})")
    if len(matches) == 1:
        name = matches[0].skill_name
        lines.append(f'Required first action: skill_view{{name: "{name}"}}.')
    else:
        names = ", ".join(f'"{m.skill_name}"' for m in matches)
        lines.append(f"Pick the best fit and call skill_view first ({names}).")
    log.info(
        "skill_route_matched",
        query_preview=user_query[:120],
        skills=[m.skill_name for m in matches],
    )
    return "\n".join(lines)


async def ensure_skill_router_ready() -> None:
    """Workspace bootstrap: rebuild skill vectors for the current workspace."""
    if not list_skills():
        return
    mark_all_skills_reindex()
    await flush_pending_skill_reindexes()
