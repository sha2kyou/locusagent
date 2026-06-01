"""Session 级冻结 system prompt 构建与缓存。"""

from __future__ import annotations

from ..artifacts import list_categories
from ..config import get_settings
from ..memory import list_memories
from ..skills import list_skills
from ..tool_settings import is_skill_enabled
from .persistence import get_session_system_prompt, set_session_system_prompt

_SNAPSHOT_MEMORY_LIMIT = 30
# 变更 build_frozen_system_prompt 模板时递增，使旧 session 缓存自动失效。
FROZEN_SYSTEM_PROMPT_VERSION = 1
_CACHE_PREFIX = f"agentpod:sp:v{FROZEN_SYSTEM_PROMPT_VERSION}:\n"


def _wrap_system_prompt_cache(prompt: str) -> str:
    return f"{_CACHE_PREFIX}{prompt}"


def _unwrap_system_prompt_cache(cached: str) -> str | None:
    if cached.startswith(_CACHE_PREFIX):
        return cached[len(_CACHE_PREFIX) :]
    return None


async def _build_memory_snapshot() -> list[str]:
    rows = await list_memories(limit=_SNAPSHOT_MEMORY_LIMIT)
    if not rows:
        return []
    rows_sorted = sorted(rows, key=lambda r: 0 if str(r.get("anchor")) == "identity" else 1)
    out: list[str] = []
    seen: set[str] = set()
    for r in rows_sorted:
        text = str(r.get("content") or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


async def build_frozen_system_prompt() -> str:
    skills = [s for s in list_skills() if is_skill_enabled(s.name)]
    settings = get_settings()
    pieces = [
        f"You are an AI agent operating in a sandboxed container for user {settings.user_id}.",
        "Use the provided tools when appropriate. Available tools: web_search, web_extract, memory, env_vars, skill_view, skill_manage, manage_workspace, session_recall, clarify, artifact_save, artifact_recall, scheduled_task_view, scheduled_task_manage, get_current_user.",
        "When a direction or preference would materially shape the output (e.g. naming, design style, scope, tech choice), ask the user via clarify{question, choices} (at most 3 options) before proceeding. Ask only ONE question per turn: call clarify at most once per turn, never in parallel; if several things need clarifying, ask them one at a time across turns. After calling clarify, end your turn immediately with no further output. Skip clarify when any reasonable choice is equally fine, or the user explicitly asks you to just proceed.",
        "Workspace files live under /data/workspace; skill files live under /data/skills.",
        "Do not perform direct filesystem operations. When file operations are required, use manage_workspace.",
        "The user cannot directly retrieve container/server files from the web UI.",
        "Deliver short or conversational outputs directly in chat as inline text or code blocks. For long-form content, structured reports, or code files, prefer artifact_save over dumping everything into chat.",
        "A compact skills catalog is listed below. When a skill is relevant to the current task, call skill_view{name} to load its full body on demand; do not assume its content.",
        "A frozen long-term memory snapshot is included below. When the user refers to a previous conversation or earlier conclusion not in the snapshot, use memory(action=recall) or session_recall to retrieve it. For credential/config KV management, use env_vars(action=add/list/update/delete/recall).",
        "Before executing code, verify required context (API keys, DB connections, timezone/path dependencies) only when the request has external dependencies. Use env_vars for credentials/config and get_current_user for runtime identity/timezone. Otherwise execute directly.",
        "When the user asks for the current date or time, use Current user local time from the Runtime Time Context system message. Do not fabricate or estimate time.",
        "When the user explicitly requests a deliverable (e.g. create, generate-and-save, export, archive, artifact), call artifact_save{title, content, type, category} to archive it. Set type to markdown/html/text by content. Category must be an existing category name; never create categories via tools. Choose the closest existing category by intent. For html-render output, pass the full [HTML_RENDER]...[/HTML_RENDER] block as content with type=html. For code, use type=markdown and always wrap in a fenced block (```<lang>\\n...code...\\n```). When the user refers to a previously saved artifact, call artifact_recall{query} first.",
    ]
    if skills:
        pieces.append("\n## Available Skills Catalog")
        for s in skills:
            triggers = ", ".join(s.triggers[:5]) if s.triggers else "-"
            desc = (s.description or "").strip() or "(no description)"
            pieces.append(f"- {s.name} [{s.source}] triggers: {triggers} · {desc}")
    categories = await list_categories()
    if categories:
        pieces.append("\n## Artifact Categories (existing)")
        pieces.append("Reuse an existing category name only; do not create new categories via tools.")
        for c in categories:
            name = str(c.get("name") or "").strip()
            if not name:
                continue
            desc = str(c.get("description") or "").strip()
            if desc:
                pieces.append(f"- {name}: {desc}")
            else:
                pieces.append(f"- {name}")
    snapshot = await _build_memory_snapshot()
    if snapshot:
        pieces.append("\n## Memory (frozen snapshot)")
        pieces.extend(f"- {m}" for m in snapshot)
    return "\n".join(pieces)


async def get_or_create_system_prompt(session_id: str) -> str:
    cached = await get_session_system_prompt(session_id)
    if cached:
        body = _unwrap_system_prompt_cache(cached)
        if body is not None:
            return body
    prompt = await build_frozen_system_prompt()
    await set_session_system_prompt(session_id, _wrap_system_prompt_cache(prompt))
    return prompt
