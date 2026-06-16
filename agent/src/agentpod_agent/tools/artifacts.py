"""产物工具：保存、召回与类目创建。"""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from ..latex_normalize import normalize_latex_input
from ..artifacts import (
    create_artifact,
    create_category,
    delete_artifact,
    delete_category,
    get_artifact,
    get_category_name,
    list_artifacts,
    list_categories,
    recall_artifacts,
    resolve_category_id,
    update_artifact,
    update_category,
)
from .args import pick_str
from .base import Tool, ToolError, ToolResult, register_builtin

_LATEX_RE = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$\n]+\$")
_CATEGORY_SIMILARITY_THRESHOLD = 0.82


def _prepare_artifact_content(content: str, art_type: str) -> str:
    """text 原样存储；latex/markdown 才做 LaTeX 转义修复。"""
    if art_type in ("latex", "markdown"):
        return normalize_latex_input(content)
    return content


def _normalize_category_name(value: str) -> str:
    # Unicode 归一化 + casefold，尽量减少“仅大小写/全半角差异”造成的重复类目。
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _category_similarity(a: str, b: str) -> float:
    na = _normalize_category_name(a)
    nb = _normalize_category_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    # 子串视为高相关，避免“报告”和“周报报告”等近重名被直接创建。
    if na in nb or nb in na:
        ratio = max(ratio, 0.9)
    return ratio


async def _resolve_category_ref(args: dict[str, Any]) -> tuple[str, str]:
    category_id = pick_str(args, "category_id", "id")
    if category_id:
        name = await get_category_name(category_id)
        if not name:
            raise ToolError(f"category not found: {category_id}")
        return category_id, name
    category = pick_str(args, "category")
    if category:
        cid = await resolve_category_id(category)
        if not cid:
            raise ToolError(f"category not found: {category}")
        return cid, category
    raise ToolError("category_id or category is required")


async def _artifact_category_create(args: dict[str, Any]) -> ToolResult:
    name = str(args.get("name", "")).strip()
    description = str(args.get("description", "")).strip()
    if not name:
        raise ToolError("name is required")

    existing = await list_categories()
    for item in existing:
        existing_name = str(item.get("name") or "").strip()
        if existing_name and _normalize_category_name(existing_name) == _normalize_category_name(name):
            return ToolResult(
                content=f"Category already exists: {existing_name}",
                metadata={"category_id": item.get("id"), "category_name": existing_name, "created": False},
            )

    similar: list[dict[str, Any]] = []
    for item in existing:
        existing_name = str(item.get("name") or "").strip()
        if not existing_name:
            continue
        score = _category_similarity(name, existing_name)
        if score >= _CATEGORY_SIMILARITY_THRESHOLD:
            similar.append({"name": existing_name, "score": round(score, 3)})
    similar.sort(key=lambda x: x["score"], reverse=True)
    similar = similar[:3]
    if similar:
        choices = [s["name"] for s in similar]
        payload = {
            "question": (
                f'About to create category "{name}", but it is similar to existing categories.'
                "Confirm whether to reuse an existing category or insist on creating a new one."
            ),
            "choices": choices + [f"Create new anyway: {name}"],
            "allow_other": False,
            "reason": "similar_category_detected",
            "candidate": name,
            "similar": similar,
        }
        raise ToolError(
            "clarify_required: detected similar categories. "
            f"Use clarify with payload={json.dumps(payload, ensure_ascii=False)}"
        )

    created = await create_category(name, description)
    created_name = str(created.get("name") or name)
    return ToolResult(
        content=f"Category created: {created_name}",
        metadata={"category_id": created.get("id"), "category_name": created_name, "created": True},
    )


async def _artifact_save(args: dict[str, Any]) -> ToolResult:
    title = str(args.get("title", "")).strip()
    content = str(args.get("content", ""))
    category = str(args.get("category", "")).strip()
    art_type = str(args.get("type", "markdown")).strip().lower() or "markdown"
    if not title:
        raise ToolError("title is required")
    if not content.strip():
        raise ToolError("content is required")

    if art_type == "html":
        raise ToolError("type=html is not supported; use markdown or text")

    content = _prepare_artifact_content(content, art_type)

    if art_type == "latex" and not _LATEX_RE.search(content):
        raise ToolError(
            "type=latex requires LaTeX delimiters: inline $...$ or block $$...$$."
        )

    if not category:
        raise ToolError(
            "category is required. Call artifact_category_create first if no category exists."
        )
    category_id = await resolve_category_id(category)
    if category_id is None:
        existing = await list_categories()
        names = [str(c.get("name") or "").strip() for c in existing]
        names = [n for n in names if n]
        if names:
            raise ToolError(
                "category_not_found: "
                f"'{category}' does not exist. Existing categories: {', '.join(names)}. "
                "Call artifact_category_create first, or reuse an existing category."
            )
        raise ToolError(
            "category_not_found: no categories exist yet. "
            "Call artifact_category_create first, then save artifacts into it."
        )

    art = await create_artifact(
        title=title, content=content, type=art_type, category_id=category_id
    )
    suffix = f" (category: {category})"
    return ToolResult(
        content=f"Artifact saved: {title}{suffix}",
        metadata={"artifact_id": art["id"], "category": category or None},
    )


async def _artifact_recall(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required")
    try:
        top_k = int(args.get("top_k", 5))
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(20, top_k))

    hits = await recall_artifacts(query, top_k)
    if not hits:
        return ToolResult(content="(no artifact hits)", metadata={"items": [], "query": query})
    lines = [
        f"- [{h.get('type')}] {h.get('title')} (id={h.get('id')}) — {h.get('snippet')}"
        for h in hits
    ]
    return ToolResult(content="\n".join(lines), metadata={"items": hits, "query": query})


async def _artifact_update(args: dict[str, Any]) -> ToolResult:
    artifact_id = pick_str(args, "id", "artifact_id")
    if not artifact_id:
        raise ToolError("id is required (use id from artifact_recall)")

    has_title = "title" in args
    has_content = "content" in args
    has_category = "category" in args
    if not has_title and not has_content and not has_category:
        raise ToolError("at least one of title, content, or category is required")

    title: str | None = None
    if has_title:
        title = str(args.get("title", "")).strip()
        if not title:
            raise ToolError("title must be non-empty when provided")

    content: str | None = None
    if has_content:
        content = str(args.get("content", ""))
        if not content.strip():
            raise ToolError("content must be non-empty when provided")
        existing = await get_artifact(artifact_id)
        art_type = str((existing or {}).get("type") or "markdown").strip().lower() or "markdown"
        content = _prepare_artifact_content(content, art_type)

    category_id: str | None = None
    if has_category:
        category = str(args.get("category", "")).strip()
        if not category:
            raise ToolError("category must be non-empty when provided")
        category_id = await resolve_category_id(category)
        if category_id is None:
            existing = await list_categories()
            names = [str(c.get("name") or "").strip() for c in existing]
            names = [n for n in names if n]
            hint = f"Existing categories: {', '.join(names)}" if names else "No categories exist."
            raise ToolError(f"category_not_found: '{category}' does not exist. {hint}")

    try:
        ok = await update_artifact(
            artifact_id,
            title=title,
            content=content,
            category_id=category_id,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if not ok:
        raise ToolError(f"artifact not found: {artifact_id}")
    return ToolResult(content=f"artifact#{artifact_id} updated", metadata={"artifact_id": artifact_id})


async def _artifact_delete(args: dict[str, Any]) -> ToolResult:
    artifact_id = pick_str(args, "id", "artifact_id")
    if not artifact_id:
        raise ToolError("id is required (use id from artifact_recall)")
    ok = await delete_artifact(artifact_id)
    if not ok:
        raise ToolError(f"artifact not found: {artifact_id}")
    return ToolResult(content=f"artifact#{artifact_id} deleted", metadata={"artifact_id": artifact_id})


async def _artifact_read(args: dict[str, Any]) -> ToolResult:
    artifact_id = pick_str(args, "id", "artifact_id")
    if not artifact_id:
        raise ToolError("id is required (use id from artifact_recall or artifact_list)")
    art = await get_artifact(artifact_id)
    if art is None:
        raise ToolError(f"artifact not found: {artifact_id}")
    category_name = await get_category_name(str(art.get("category_id") or ""))
    category_label = category_name or str(art.get("category_id") or "")
    header = (
        f"# {art.get('title')} [{art.get('type')}] (id={art.get('id')}, category={category_label})\n\n"
    )
    return ToolResult(
        content=header + str(art.get("content") or ""),
        metadata={"item": art},
    )


async def _artifact_list(args: dict[str, Any]) -> ToolResult:
    category_id, category_name = await _resolve_category_ref(args)
    try:
        limit = int(args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(200, limit))
    rows = await list_artifacts(category_id)
    rows = rows[:limit]
    if not rows:
        return ToolResult(
            content=f"(empty category: {category_name})",
            metadata={"items": [], "category_id": category_id, "category": category_name},
        )
    lines = [
        f"- [{r.get('type')}] {r.get('title')} (id={r.get('id')})"
        for r in rows
    ]
    return ToolResult(
        content="\n".join(lines),
        metadata={"items": rows, "category_id": category_id, "category": category_name},
    )


async def _artifact_category_update(args: dict[str, Any]) -> ToolResult:
    category_id, current_name = await _resolve_category_ref(args)
    has_name = "name" in args
    has_description = "description" in args
    if not has_name and not has_description:
        raise ToolError("at least one of name or description is required")
    name: str | None = None
    if has_name:
        name = str(args.get("name", "")).strip()
        if not name:
            raise ToolError("name must be non-empty when provided")
    description: str | None = None
    if has_description:
        description = str(args.get("description", ""))
    ok = await update_category(category_id, name=name, description=description)
    if not ok:
        raise ToolError(f"category not found: {category_id}")
    label = name or current_name
    return ToolResult(
        content=f"category#{category_id} updated ({label})",
        metadata={"category_id": category_id, "category_name": label},
    )


async def _artifact_category_delete(args: dict[str, Any]) -> ToolResult:
    category_id, category_name = await _resolve_category_ref(args)
    ok = await delete_category(category_id)
    if not ok:
        raise ToolError(f"category not found: {category_id}")
    return ToolResult(
        content=f"category#{category_id} deleted ({category_name})",
        metadata={"category_id": category_id, "category_name": category_name},
    )


register_builtin(
    Tool(
        name="artifact_category_create",
        description=(
            "Create an artifact category. "
            "If highly similar to an existing category, clarify first (reuse vs create new) before proceeding."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Category name to create."},
                "description": {"type": "string", "description": "Optional category description."},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_artifact_category_create,
    )
)


register_builtin(
    Tool(
        name="artifact_recall",
        description=(
            "Search historical artifacts (reports, copy, code drafts, visualizations, etc.). "
            "Prefer when the user asks to find prior work, continue from a saved artifact, or compare versions. "
            "Returns candidates (title/type/id/snippet) for you to process by id or title. "
            "Do not use for one-off turn output that does not need persistence."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords or natural-language intent (e.g. last recruiting poster copy).",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Max candidates (1-20). Higher recall may add noise.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=_artifact_recall,
    )
)


register_builtin(
    Tool(
        name="artifact_save",
        description=(
            "Save this turn's result as a reusable artifact for later recall and iteration. "
            "For deliverable outputs: reports, plans, copy, scripts, page snippets, etc. "
            "category archives by type (e.g. content, reports); call artifact_category_create if missing. "
            "Not for temporary explanations or one-off chat replies. "
            "After save, briefly confirm in reply—no links."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Artifact title; should be searchable later."},
                "content": {"type": "string", "description": "Artifact body (persisted)."},
                "type": {
                    "type": "string",
                    "enum": ["markdown", "latex", "text"],
                    "description": (
                        "Render type: markdown=Markdown; latex=LaTeX (inline $...$, block $$...$$); "
                        "text=plain (no Markdown/LaTeX rendering). "
                        "markdown/text do not validate $; use latex for formulas. "
                        "Escape backslashes twice in JSON (\\\\begin)."
                    ),
                },
                "category": {
                    "type": "string",
                    "description": "Archive category name (e.g. content, reports). Must exist or create via artifact_category_create.",
                },
            },
            "required": ["title", "content", "category"],
        },
        handler=_artifact_save,
    )
)


register_builtin(
    Tool(
        name="artifact_update",
        description=(
            "Update an artifact by id from artifact_recall. "
            "Provide at least one of title, content, category (category is the category name)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Artifact id (id=... from artifact_recall).",
                },
                "title": {"type": "string", "description": "New title."},
                "content": {"type": "string", "description": "New body."},
                "category": {
                    "type": "string",
                    "description": "Target category name (must exist).",
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        handler=_artifact_update,
    )
)


register_builtin(
    Tool(
        name="artifact_delete",
        description="Delete artifact by id from artifact_recall.",
        parameters={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Artifact id (id=... from artifact_recall).",
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        handler=_artifact_delete,
    )
)


register_builtin(
    Tool(
        name="artifact_read",
        description="Read full artifact by id from artifact_recall or artifact_list.",
        parameters={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Artifact id (id=... from artifact_recall / artifact_list).",
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        handler=_artifact_read,
    )
)


register_builtin(
    Tool(
        name="artifact_list",
        description="List artifacts by category (id/title/type). Use category name or category_id.",
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category name."},
                "category_id": {"type": "string", "description": "Category id."},
                "limit": {"type": "integer", "default": 50, "description": "Max rows (1-200)."},
            },
            "additionalProperties": False,
        },
        handler=_artifact_list,
    )
)


register_builtin(
    Tool(
        name="artifact_category_update",
        description="Update artifact category name or description by category_id or category.",
        parameters={
            "type": "object",
            "properties": {
                "category_id": {"type": "string", "description": "Category id."},
                "category": {"type": "string", "description": "Category name when id unknown."},
                "name": {"type": "string", "description": "New category name."},
                "description": {"type": "string", "description": "New description."},
            },
            "additionalProperties": False,
        },
        handler=_artifact_category_update,
    )
)


register_builtin(
    Tool(
        name="artifact_category_delete",
        description="Delete category and all its artifacts by category_id or category.",
        parameters={
            "type": "object",
            "properties": {
                "category_id": {"type": "string", "description": "Category id."},
                "category": {"type": "string", "description": "Category name when id unknown."},
            },
            "additionalProperties": False,
        },
        handler=_artifact_category_delete,
    )
)
