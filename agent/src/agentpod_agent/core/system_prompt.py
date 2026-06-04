"""Session 级冻结 system prompt 构建与缓存。"""

from __future__ import annotations

import hashlib
import json

from ..artifacts import list_categories
from ..config import get_settings
from ..memory import list_memories
from ..skills import list_skills
from ..logging import get_logger
from ..tool_settings import is_skill_enabled, load_tool_settings
from ..tools import registry as tool_registry
from ..workspace import get_workspace_id
from .persistence import get_session_system_prompt, set_session_system_prompt

log = get_logger("system_prompt")

_SNAPSHOT_MEMORY_LIMIT = 30
# 变更 build_frozen_system_prompt 模板时递增，使旧 session 缓存自动失效。
FROZEN_SYSTEM_PROMPT_VERSION = 11
_CACHE_PREFIX = f"agentpod:sp:v{FROZEN_SYSTEM_PROMPT_VERSION}:"


def _format_available_tools() -> str:
    tools = tool_registry.list(workspace_id=get_workspace_id())
    return ", ".join(sorted(t.name for t in tools))


async def _compute_snapshot_fingerprint() -> str:
    tool_settings = load_tool_settings()
    enabled_tools = sorted(t.name for t in tool_registry.list(workspace_id=get_workspace_id()))
    skills = sorted(
        f"{s.name}:{(s.description or '').strip()}"
        for s in list_skills()
        if is_skill_enabled(s.name)
    )
    category_rows = await list_categories()
    categories = sorted(
        f"{str(c.get('name') or '').strip()}:{str(c.get('description') or '').strip()}"
        for c in category_rows
        if str(c.get("name") or "").strip()
    )
    memories = await list_memories(limit=_SNAPSHOT_MEMORY_LIMIT)
    memory_lines = sorted(str(m.get("content") or "").strip() for m in memories if m.get("content"))
    payload = {
        "tools": enabled_tools,
        "tool_settings": tool_settings.to_dict(),
        "skills": skills,
        "categories": categories,
        "memory": memory_lines,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:16]


def _wrap_system_prompt_cache(prompt: str, fingerprint: str) -> str:
    return f"{_CACHE_PREFIX}{fingerprint}:\n{prompt}"


def _unwrap_system_prompt_cache(cached: str, fingerprint: str) -> str | None:
    expected_prefix = f"{_CACHE_PREFIX}{fingerprint}:"
    if cached.startswith(expected_prefix):
        return cached[len(expected_prefix) + 1 :]
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
        mid = int(r.get("id") or 0)
        if text and text not in seen:
            seen.add(text)
            label = "user" if str(r.get("anchor")) == "identity" else "memory"
            out.append(f"#{mid} [{label}] {text}")
    return out


async def build_frozen_system_prompt() -> str:
    skills = [s for s in list_skills() if is_skill_enabled(s.name)]
    settings = get_settings()
    tool_names = _format_available_tools()
    pieces = [
        f"You are an AI agent operating in a sandboxed container for user {settings.user_id}.",
        f"Use the provided tools when appropriate. Available tools: {tool_names}.",
        "When a direction or preference would materially shape the output (e.g. naming, design style, scope, tech choice), ask the user via clarify with strict JSON arguments {question, choices, allow_other} (2–4 mutually exclusive choices; single-select). Put every selectable option in choices, not in question. Ask only ONE question per turn: call clarify at most once per turn, never in parallel; if several things need clarifying, ask them one at a time across turns. After a successful clarify call, end your turn immediately with no further output. Skip clarify when options cannot be enumerated, the user must pick multiple items, any reasonable choice is equally fine, or the user explicitly asks you to just proceed.",
        "Workspace files live under workspace/ relative to the container data directory; skill files live under /data/skills.",
        "For file operations within the workspace, use read_file, search_files, write_file, and patch.",
        "Use manage_workspace for MCP server configuration and environment summary only—not for creating, deleting, renaming, or switching AgentPod workspaces (multi-workspace containers). "
        "You operate in the user's current workspace only; if they ask to create/delete/rename/switch workspaces during chat, refuse and tell them to use the Web UI 「工作区」 page outside chat.",
        "The user cannot directly retrieve container/server files from the web UI.",
        "Deliver outputs directly in chat as inline text or code blocks unless the user explicitly asks to save, export, or archive.",
        "For math in chat, use LaTeX for frontend rendering: inline $...$, block-level $$...$$ on its own line (blank line before/after each block). Do not substitute Unicode symbols or put formulas in ordinary code fences. Use \\\\ for row/line breaks inside environments (pmatrix, cases, aligned). Example matrix: $$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$$; example cases: $$\\begin{cases} x + y = 5 \\\\ 2x - y = 1 \\end{cases}$$.",
        "A compact skills catalog is listed below. When a skill is relevant to the current task, call skill_view{name} to load its full body on demand; do not assume its content.",
        "A frozen long-term memory snapshot is included below (each line shows #id [user|memory]). "
        "Save new durable facts via memory(action=add) or update existing ones via memory(action=replace, id=..., content=...) "
        "when they match the memory tool criteria (preferences, corrections, stable setup)—never auto-log one-off Q&A. "
        "When the user refers to a previous conversation or earlier conclusion not in the snapshot, use memory(action=recall) or session_recall. "
        "For credential/config KV management, use env_vars(action=add/list/update/delete/recall); "
        "update/delete prefer id from list/recall, or exact name."
        "Before executing code, verify required context (API keys, DB connections, timezone/path dependencies) only when the request has external dependencies. Use env_vars for credentials/config and get_current_user for runtime identity/timezone. Otherwise execute directly.",
        "When the user asks for the current date or time, use Current user local time from the Runtime Time Context system message. Do not fabricate or estimate time.",
        "When the user explicitly requests a deliverable (e.g. create, generate-and-save, export, archive, artifact), call artifact_save{title, content, type, category} to archive it. Set type explicitly by render need: markdown (headings/lists/code fences only), latex (math via inline $...$ or block $$...$$—not Markdown syntax), html (interactive/page markup), text (plain text, no rendering). Content with LaTeX/math MUST use type=latex with $/$$ delimiters, never markdown or text. In artifact_save JSON arguments, escape backslashes twice for LaTeX commands (write \\\\begin not \\begin). If category is provided, you MUST read and follow that category's description in 'Artifact Categories (existing)' when drafting content (this is prompt guidance, do not inject category description text into the artifact body unless the user asks for it). If the target category does not exist, call artifact_category_create{name, description} first. If artifact_category_create reports similar existing categories, call clarify before deciding to reuse or create. For code, use type=markdown and always wrap in a fenced block (```<lang>\\n...code...\\n```). When the user refers to a previously saved artifact, call artifact_recall{query} first. After artifact_save succeeds, summarize in your reply and include the artifact link from the tool result. [HTML_RENDER] html-render output is for in-chat display only; do not artifact_save it unless the user explicitly asks to save/export/archive that HTML.",
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
        pieces.append(
            "Prefer reusing existing category names. Create a new one via artifact_category_create only when needed."
        )
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
    fingerprint = await _compute_snapshot_fingerprint()
    cached = await get_session_system_prompt(session_id)
    if cached:
        body = _unwrap_system_prompt_cache(cached, fingerprint)
        if body is not None:
            return body
    prompt = await build_frozen_system_prompt()
    await set_session_system_prompt(session_id, _wrap_system_prompt_cache(prompt, fingerprint))
    return prompt
