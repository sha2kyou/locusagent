"""System prompt three-tier dynamic assembly with session-level cache (Hermes stable/context/volatile).

- stable: identity, tool rules, skill catalog, artifact categories — cached per session for prefix cache warmth
- context: workspace resource summary (skills/MCP/memory/env/scheduled tasks/artifacts), rebuilt each turn
- volatile: memory snapshot, session metadata — rebuilt each turn; visible next turn after memory writes
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TypedDict

from ..artifacts import list_categories
from ..config import get_settings
from ..host_settings import get_timezone
from ..memory import list_memories, memory_term_label
from ..skills import list_skills
from ..logging import get_logger
from ..tool_settings import is_skill_enabled, load_tool_settings
from ..tools import registry as tool_registry
from ..workspace import get_workspace_id
from .persistence import get_session_system_prompt, set_session_system_prompt

log = get_logger("system_prompt")

_SNAPSHOT_MEMORY_LIMIT = 30
_CTX_DELIMITER = "\n<<AGENTPOD_CTX>>\n"
# Bump when stable template changes so old session caches invalidate.
FROZEN_SYSTEM_PROMPT_VERSION = 28
_CACHE_PREFIX = f"agentpod:sp:v{FROZEN_SYSTEM_PROMPT_VERSION}:"

MEMORY_GUIDANCE = (
    "You have persistent memory across sessions. Use the memory tool to save long-lived facts: "
    "user preferences, environment details, stable conventions. "
    "A memory snapshot is injected every turn—entries should be compact and only keep what still "
    "matters later; prioritize facts that reduce repeated user reminders.\n"
    "Do not save task progress, session outcomes, completion logs, or temporary state; "
    "use session_recall or session_search for past conversations. "
    "Do not record PR numbers, issue numbers, commit hashes, or anything stale within a week. "
    "If you discover reusable techniques or workflows, write a private skill instead of memory.\n"
    "Write memories as declarative facts. term=long_term for stable user facts and preferences "
    "(long-term memory); term=short_term for persistent operational notes (short-term memory)."
)

SKILLS_GUIDANCE = (
    "A compact skill catalog is listed below. When a skill is relevant, call skill_view{name} to "
    "load the full SKILL.md on demand; do not guess its contents. "
    "For references/, scripts/, or assets/ files listed in the skill, call "
    "skill_view{name, file_path} to load them progressively. "
    "To install a skill from GitHub, a zip URL, or a direct SKILL.md link into the workspace, use skill_install. "
    "Only private skills may be modified via skill_manage; shared and built-in skills are read-only."
)

SESSION_SEARCH_GUIDANCE = (
    "When the user mentions past conversations or conclusions not in the memory snapshot, "
    "use session_recall or session_search first—do not guess."
)

ARTIFACT_GUIDANCE = (
    "Use artifact_save for deliverables the user explicitly asks to save or archive. "
    "Use deliver_file for downloadable workspace files. "
    "When the user mentions a saved artifact, call artifact_recall{query} first."
)

TOOL_LOOP_LIMIT_GUIDANCE = (
    "When tool-call rounds, loop guardrails, or context limits force you to stop calling tools, "
    "you must give the user a complete summary response based on the conversation and tool results so far: "
    "progress made, current conclusions, unfinished items and why, and suggested next steps. "
    "Do not end silently, do not return an empty reply, and do not attempt more tool calls."
)


class SystemPromptParts(TypedDict):
    stable: str
    context: str
    volatile: str


def _format_available_tools() -> set[str]:
    return {t.name for t in tool_registry.list(workspace_id=get_workspace_id())}


async def _compute_stable_fingerprint() -> str:
    tool_settings = load_tool_settings()
    enabled_tools = sorted(_format_available_tools())
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
    payload = {
        "tools": enabled_tools,
        "tool_settings": tool_settings.to_dict(),
        "skills": skills,
        "categories": categories,
        "version": FROZEN_SYSTEM_PROMPT_VERSION,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:16]


def _wrap_stable_context_cache(stable: str, context: str, fingerprint: str) -> str:
    return f"{_CACHE_PREFIX}{fingerprint}:\n{stable}{_CTX_DELIMITER}{context}"


def _unwrap_stable_context_cache(cached: str, fingerprint: str) -> tuple[str, str] | None:
    expected_prefix = f"{_CACHE_PREFIX}{fingerprint}:"
    if not cached.startswith(expected_prefix):
        return None
    body = cached[len(expected_prefix) + 1 :]
    if _CTX_DELIMITER not in body:
        return None
    stable, context = body.split(_CTX_DELIMITER, 1)
    return stable, context


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
            label = memory_term_label(r.get("anchor"))
            out.append(f"#{mid} [{label}] {text}")
    return out


async def build_stable_prompt() -> str:
    skills = [s for s in list_skills() if is_skill_enabled(s.name)]
    settings = get_settings()
    tool_names = sorted(_format_available_tools())
    enabled = set(tool_names)
    pieces = [
        "You are an AI agent running in the AgentPod desktop app.",
        f"Use the provided tools when appropriate. Available tools: {', '.join(tool_names)}.",
        "Call tools only via native tool_calls—never write tool invocations in message body text. "
        "Do not output pseudo tool tags, pseudo function calls, pseudo arguments, JSON tool stubs, "
        "or any text-form tool simulation; such content will not execute. "
        "When you need a tool, emit tool_calls; keep body empty or user-facing prose only.",
        "Parallel tool calls: when multiple tool calls are independent (one's output is not required "
        "as another's input), emit multiple tool_calls in the same assistant turn—they run in parallel. "
        "When the user asks to fetch, search, or read several things at once, prefer parallel calls "
        "over one tool per turn "
        "(e.g. multiple read_file paths, multiple URLs, search_files plus web_search, MCP read/list ops). "
        "Do not wait for round N to issue independent calls that could have run in parallel in round N+1. "
        "Exception: clarify must be called alone, never in parallel; after a successful clarify, end the turn immediately. "
        "Do not parallelize state-mutating tools or calls with sequential dependencies.",
        TOOL_LOOP_LIMIT_GUIDANCE,
        "When direction or preferences materially affect output (naming, design style, scope, tech choices), "
        "ask the user via clarify with strict JSON: {question, choices, allow_other} (2–4 mutually exclusive options, single-select). "
        "Put all options in choices, not in question. "
        "At most one question per turn: at most one clarify per turn, never parallel; "
        "if multiple clarifications are needed, ask across turns. End the turn immediately after a successful clarify. "
        "Skip clarify when options cannot be enumerated, the user must multi-select, any reasonable choice works, "
        "or the user explicitly asks you to proceed.",
        "For multi-step tasks use the todo tool; follow when to break down vs skip in the todo tool description.",
        "Workspace files live under workspace/ in the current workspace; private skills under skills/.",
        "Use read_file, search_files, write_file, patch for workspace file ops.",
        "manage_workspace is only for MCP server config and environment summary—"
        "never for creating, deleting, renaming, or switching AgentPod workspaces. "
        "You operate only in the user's current workspace; if they ask to create/delete/rename/switch workspaces in chat, "
        "refuse and tell them to use the Workspaces page outside chat.",
        "The user cannot browse the local filesystem directly from the UI.",
        "Unless the user explicitly asks to save, export, or archive, deliver results in chat as body text or code blocks. "
        "When the user needs a downloadable workspace file (documents, archives, spreadsheets, binaries), "
        "write to workspace/ and call deliver_file—not artifact_save. "
        "The chat UI shows a download entry automatically; after deliver_file succeeds do not mention the file in your reply: "
        "do not say you sent it, do not write the filename, Markdown/HTTP links, artifact paths, or attachment ids. "
        "At most one optional sentence describing file contents if the user needs context.",
        "Use LaTeX in chat for math so the frontend can render: inline $...$, display $$...$$ on its own lines "
        "(blank line before and after block math). "
        "Do not substitute plain Unicode for formulas or put formulas in ordinary code fences. "
        "Use \\\\ for line breaks inside matrix/cases environments. "
        "Example matrix: $$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$$; "
        "example piecewise: $$\\begin{cases} x + y = 5 \\\\ 2x - y = 1 \\end{cases}$$.",
        "Before executing code, verify required context (API keys, DB connections, timezone or path deps) "
        "only when the request depends on external resources. "
        "Use env_vars to store credentials/config; pass env var names to execute_code or terminal when needed "
        "(values inject at runtime—do not recall into code). "
        "Use get_current_user for runtime identity and timezone; otherwise execute directly.",
        "When the user asks for the current date or time, use the runtime context's current user local time—do not invent or estimate.",
        "When the user explicitly requests a deliverable (create, generate and save, export, archive, artifact), "
        "archive with artifact_save. "
        "Set type explicitly by rendering need: markdown (Markdown), latex (LaTeX/math, inline $...$ or block $$...$$), "
        "text (plain text, no Markdown or LaTeX rendering, stored and shown as-is). "
        "In artifact_save JSON params, escape LaTeX backslashes twice (e.g. \\\\begin not \\begin). "
        "If category is provided, read and follow that category's description under Artifact categories (existing) below when drafting "
        "(guidance only—do not paste category description into artifact body unless the user asks). "
        "If the target category does not exist, call artifact_category_create first. "
        "If artifact_category_create reports a similar category, clarify before reusing or creating new. "
        "For code artifacts use type=markdown with body wrapped in a code fence (```lang\\n...code...\\n```). "
        "After artifact_save succeeds, briefly confirm saved—do not include artifact links.",
    ]
    tool_guidance: list[str] = []
    if "memory" in enabled:
        tool_guidance.append(MEMORY_GUIDANCE)
    if "session_search" in enabled or "session_recall" in enabled:
        tool_guidance.append(SESSION_SEARCH_GUIDANCE)
    if "skill_view" in enabled or "skill_manage" in enabled or "skill_install" in enabled:
        tool_guidance.append(SKILLS_GUIDANCE)
    if "artifact_save" in enabled:
        tool_guidance.append(ARTIFACT_GUIDANCE)
    if tool_guidance:
        pieces.append(" ".join(tool_guidance))
    if skills:
        pieces.append("\n## Available skills catalog")
        for s in skills:
            triggers = ", ".join(s.triggers[:5]) if s.triggers else "none"
            desc = (s.description or "").strip() or "(no description)"
            pieces.append(f"- {s.name} [{s.source}] triggers: {triggers} · {desc}")
    categories = await list_categories()
    if categories:
        pieces.append("\n## Artifact categories (existing)")
        pieces.append(
            "Prefer reusing existing category names; create new ones via artifact_category_create only when necessary."
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
    return "\n".join(pieces)


_CONTEXT_HEADER = (
    "Below is a read-only snapshot of current workspace resources; env vars list names and descriptions only, not values. "
    "Use dedicated tools (manage_workspace, env_vars, mcp_manage, etc.) for full lists or edits."
)


async def build_context_prompt(*, session_id: str | None = None) -> str:
    """Context tier: workspace resource summary, same source as manage_workspace tool."""
    _ = session_id
    from ..workspace import get_workspace_id
    from ..workspace_summary import build_workspace_summary

    summary, _ = await build_workspace_summary()
    if not summary.strip():
        return ""
    wid = get_workspace_id()
    return f"## Workspace context ({wid})\n{_CONTEXT_HEADER}\n\n{summary}"


async def build_volatile_prompt(*, session_id: str | None = None) -> str:
    """Volatile tier: memory snapshot and session metadata, rebuilt each turn."""
    parts: list[str] = []
    snapshot = await _build_memory_snapshot()
    if snapshot:
        parts.append("## Memory (current snapshot)")
        parts.append(
            "Each line: #id [long-term|short-term]. "
            "Add with memory(action=add); update with memory(action=replace, id=..., content=...). "
            "Use env_vars for credentials; pass names to execute_code/terminal env param when running code."
        )
        parts.extend(f"- {m}" for m in snapshot)
    now_utc = datetime.now(UTC)
    date_line = f"Conversation date: {now_utc.strftime('%Y-%m-%d')} (UTC)"
    try:
        tz_name = await get_timezone()
        date_line += f"\nUser timezone: {tz_name}"
    except Exception:
        pass
    if session_id:
        date_line += f"\nSession id: {session_id}"
    parts.append(date_line)
    return "\n".join(parts)


async def build_system_prompt_parts(*, session_id: str | None = None) -> SystemPromptParts:
    return {
        "stable": await build_stable_prompt(),
        "context": await build_context_prompt(session_id=session_id),
        "volatile": await build_volatile_prompt(session_id=session_id),
    }


def assemble_system_prompt(parts: SystemPromptParts) -> str:
    return "\n\n".join(p.strip() for p in (parts["stable"], parts["context"], parts["volatile"]) if p and p.strip())


async def _get_or_create_stable_context(session_id: str) -> tuple[str, str]:
    fingerprint = await _compute_stable_fingerprint()
    cached = await get_session_system_prompt(session_id)
    if cached:
        parsed = _unwrap_stable_context_cache(cached, fingerprint)
        if parsed is not None:
            return parsed
    stable = await build_stable_prompt()
    context = await build_context_prompt(session_id=session_id)
    await set_session_system_prompt(
        session_id,
        _wrap_stable_context_cache(stable, context, fingerprint),
    )
    return stable, context


async def get_cached_stable_context(session_id: str) -> SystemPromptParts:
    """For background review fork: inherit parent session stable+context (no volatile)."""
    stable, context = await _get_or_create_stable_context(session_id)
    return {"stable": stable, "context": context, "volatile": ""}


async def get_or_create_system_prompt(session_id: str) -> str:
    stable, _ = await _get_or_create_stable_context(session_id)
    context = await build_context_prompt(session_id=session_id)
    volatile = await build_volatile_prompt(session_id=session_id)
    return assemble_system_prompt({"stable": stable, "context": context, "volatile": volatile})


# Back-compat for older tests and callers
def _wrap_system_prompt_cache(prompt: str, fingerprint: str) -> str:
    return _wrap_stable_context_cache(prompt, "", fingerprint)


def _unwrap_system_prompt_cache(cached: str, fingerprint: str) -> str | None:
    parsed = _unwrap_stable_context_cache(cached, fingerprint)
    if parsed is None:
        return None
    stable, context = parsed
    return assemble_system_prompt({"stable": stable, "context": context, "volatile": ""})


async def build_frozen_system_prompt() -> str:
    """Back-compat: full three-tier assembly (volatile live)."""
    parts = await build_system_prompt_parts()
    return assemble_system_prompt(parts)
