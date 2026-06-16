"""memory 工具：长期记忆增删改查 + 召回。"""

from __future__ import annotations

from typing import Any

from ..core.write_origin import ORIGIN_AUTO_EXTRACT, ORIGIN_MANUAL, is_auto_extract_write
from ..memory import (
    add_memory,
    delete_memory,
    enqueue_embedding,
    list_memories,
    memory_term_label,
    recall_items,
    resolve_memory_anchor_input,
    update_memory,
)
from ..security import review_write
from .args import pick_action, pick_int, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


def _require_memory_id(args: dict[str, Any]) -> int:
    mid = pick_int(args, "id")
    if mid:
        return mid
    raise ToolError("id is required (from snapshot/read/list/recall)")


async def _memory_tool(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)
    raw_term = pick_str(args, "term") or "short_term"
    try:
        anchor = resolve_memory_anchor_input(raw_term)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    term_label = memory_term_label(anchor)

    if action == "add":
        content = pick_str(args, "content")
        if not content:
            raise ToolError("content is required for add")
        verdict = await review_write(content, kind="memory")
        if not verdict.allowed:
            raise ToolError(f"memory write blocked by guard: {verdict.reason}")
        mid = await add_memory(
            content,
            anchor=anchor,
            origin=ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else ORIGIN_MANUAL,
        )
        await enqueue_embedding(mid)
        saved_origin = ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else ORIGIN_MANUAL
        origin_label = " [auto_extract]" if saved_origin == ORIGIN_AUTO_EXTRACT else ""
        return ToolResult(content=f"memory#{mid} saved ({term_label}){origin_label}")

    if action == "replace":
        content = pick_str(args, "content")
        if not content:
            raise ToolError("content is required for replace")
        mid = _require_memory_id(args)
        verdict = await review_write(content, kind="memory")
        if not verdict.allowed:
            raise ToolError(f"memory write blocked by guard: {verdict.reason}")
        write_origin = ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else None
        ok = await update_memory(mid, content, anchor=anchor, origin=write_origin)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        await enqueue_embedding(mid, bump=True)
        origin_label = " [auto_extract]" if write_origin == ORIGIN_AUTO_EXTRACT else ""
        return ToolResult(content=f"memory#{mid} replaced ({term_label}){origin_label}")

    if action == "remove":
        mid = _require_memory_id(args)
        ok = await delete_memory(mid)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        return ToolResult(content=f"memory#{mid} removed")

    if action == "read":
        rows = await list_memories(limit=int(args.get("limit", 100) or 100))
        scoped = [r for r in rows if str(r.get("anchor") or "experience") == anchor]
        if not scoped:
            return ToolResult(content="(empty)")
        return ToolResult(
            content="\n".join(
                f"- #{r['id']} [{memory_term_label(r.get('anchor'))}] {r['content']}" for r in scoped
            ),
            metadata={"items": scoped},
        )

    if action == "list":
        rows = await list_memories(limit=int(args.get("limit", 50) or 50))
        if not rows:
            return ToolResult(content="(empty)")
        return ToolResult(
            content="\n".join(
                f"#{r['id']}[{memory_term_label(r.get('anchor'))}][{r['embedding_state']}] {r['content']}"
                for r in rows
            ),
            metadata={"items": rows},
        )

    if action == "recall":
        query = pick_str(args, "query")
        if not query:
            raise ToolError("query is required for recall")
        top_k = int(args.get("top_k", 5) or 5)
        hits = await recall_items(query, top_k=top_k)
        scoped = [h for h in hits if str(h.get("anchor") or "experience") == anchor]
        if not scoped:
            return ToolResult(content="(no recall hits)")
        return ToolResult(
            content="\n".join(
                f"- #{h['id']} [{memory_term_label(h.get('anchor'))}] {h['content']}" for h in scoped
            ),
            metadata={"items": scoped},
        )

    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="memory",
        description=(
            "Persist cross-session reusable information in long-term memory; memories inject into later turns—"
            "keep entries short and only what stays useful long-term.\n\n"
            "Save proactively (without waiting for the user) when:\n"
            "- the user corrects you or says remember / don't do that again\n"
            "- the user shares preferences, habits, or background (name, role, timezone, coding style, etc.)\n"
            "- you learn environment facts (OS, installed tools, project layout)\n"
            "- you find workflow-specific conventions, API quirks, or stable config for this user\n\n"
            "Priority: user preferences and corrections > environment facts > procedural knowledge.\n\n"
            "Do not save: single Q&A summaries, task progress, session outcomes, completion logs, temporary TODOs—"
            "use session_recall for those. Reusable techniques belong in skills.\n\n"
            "term (matches Memory UI): long_term or short_term only.\n"
            "Actions: add / replace / remove / read / list / recall.\n"
            "For replace/remove: id is required (from snapshot/read/list/recall)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "add",
                        "replace",
                        "remove",
                        "read",
                        "list",
                        "recall",
                    ],
                },
                "term": {
                    "type": "string",
                    "enum": ["long_term", "short_term"],
                    "default": "short_term",
                    "description": "long_term or short_term; matches Memory UI.",
                },
                "id": {
                    "type": "integer",
                    "description": "Entry id from snapshot, read, list, or recall. Required for replace/remove.",
                },
                "content": {
                    "type": "string",
                    "description": "Full text for add/replace.",
                },
                "query": {"type": "string", "description": "Required for recall."},
                "top_k": {"type": "integer", "default": 5},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["action"],
        },
        handler=_memory_tool,
    )
)
