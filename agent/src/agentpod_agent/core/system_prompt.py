"""Session 级冻结 system prompt 构建与缓存。"""

from __future__ import annotations

from ..artifacts import list_categories
from ..config import get_settings
from ..memory import list_memories
from ..skills import list_skills
from ..tool_settings import is_skill_enabled
from .persistence import get_session_system_prompt, set_session_system_prompt

_SNAPSHOT_MEMORY_LIMIT = 30


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
        "Use the provided tools (web_search/web_extract/memory/env_vars/skill_view/skill_manage/manage_workspace/session_recall/clarify/artifact_save/artifact_recall/scheduled_task_view/scheduled_task_manage) when appropriate.",
        "When there are multiple reasonable interpretations of the request, or when a direction/preference would materially shape the output (e.g. naming, design style, scope, tech choice), prefer to first ask the user via clarify{question, options} (at most 3 options) for that direction rather than assuming or dumping every possible option. This applies even to open-ended requests like 'give me some suggestions'. Ask only ONE question per turn: call clarify at most once and never in parallel; if several things need clarifying, ask them one at a time across turns. After calling clarify, immediately end your turn and output no further text; the user's selection will arrive as the next message. Only skip clarify when any reasonable choice is equally fine or the user explicitly asks you to just proceed.",
        "Workspace files live under /data/workspace; private skills live under /data/skills.",
        "Do not perform any file CRUD operations: no file read/list/search/create/update/patch/delete in container or workspace.",
        "The user cannot directly retrieve container/server files from the web UI.",
        "By default, do not create or modify files in workspace.",
        "Deliver outputs directly in chat as inline text, code blocks, and step-by-step instructions.",
        "A compact skills catalog is listed below. When a skill is relevant to the current task, call skill_view{name} to load its full body on demand; do not assume its content.",
        "A frozen long-term memory snapshot is included below. When the user refers to a previous conversation or an earlier conclusion not covered by the snapshot, use memory(action=recall) or session_recall to retrieve it instead of guessing. For credential/config KV management, use env_vars(action=add/list/update/delete/recall).",
        "When the user explicitly asks to produce or save a deliverable (e.g. 创建广告/生成报告/写文案/图表/代码, 保存为某个产物类别), call artifact_save{title, content, type, category} to archive it; set type to markdown/html/text by content, choose category by intent (e.g. 广告/报告/图表/代码). If a category has description text, treat that description as the primary routing hint; if description is empty, use category name only. IMPORTANT: category must be an existing category name; do NOT create new categories via tool calls. If needed, ask the user to create the category in UI first. For visualizations produced via the html-render skill, pass the full [HTML_RENDER]...[/HTML_RENDER] block as content (the tool stores its inner HTML as type=html). When the deliverable is code, use type=markdown and ALWAYS wrap the code in a fenced block (```<lang>\\n...code...\\n```) so it renders with syntax highlighting; never store raw unfenced code. Do this only on an explicit produce request, not for ordinary answers. When the user refers to a previously produced artifact (e.g. 之前的报告/那个图表/继续上次的代码), call artifact_recall{query} to locate it by title before answering.",
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
        return cached
    prompt = await build_frozen_system_prompt()
    await set_session_system_prompt(session_id, prompt)
    return prompt
