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

_HTML_RENDER_RE = re.compile(r"\[HTML_RENDER\]([\s\S]*?)\[/HTML_RENDER\]", re.IGNORECASE)
_LATEX_RE = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$\n]+\$")
_CATEGORY_SIMILARITY_THRESHOLD = 0.82


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
                content=f"类目已存在：{existing_name}",
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
                f"准备创建新类目“{name}”，但它与已有类目相似。"
                "请确认应复用已有类目，还是坚持创建新类目？"
            ),
            "choices": choices + [f"坚持新建：{name}"],
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
        content=f"类目已创建：{created_name}",
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

    # content 可带 [HTML_RENDER] 包裹：剥离标记后按 html 类型保存
    m = _HTML_RENDER_RE.search(content)
    if m:
        content = m.group(1).strip()
        art_type = "html"

    content = normalize_latex_input(content)

    if art_type == "text" and _LATEX_RE.search(content):
        raise ToolError(
            "type=text does not render LaTeX. Use type=latex for content with $...$ or $$...$$ formulas."
        )
    if art_type == "markdown" and _LATEX_RE.search(content):
        raise ToolError(
            "type=markdown must not contain $...$ or $$...$$. Use type=latex for math content."
        )
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
    suffix = f"（类目：{category}）"
    return ToolResult(
        content=f"产物已保存：{title}{suffix}",
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
        m = _HTML_RENDER_RE.search(content)
        if m:
            content = m.group(1).strip()
        content = normalize_latex_input(content)

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
            "创建产物类目。"
            "若与现有类目高度相似，必须先澄清目标（复用已有类目或坚持新建）再继续。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "要创建的类目名。"},
                "description": {"type": "string", "description": "类目描述，可选。"},
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
            "检索历史产物（报告/文案/代码草稿/可视化结果等）。"
            "当用户要求“找回之前做过的内容”“基于上次产物继续修改”“对比历史版本”时优先调用。"
            "输入 query 后返回候选产物（title/type/id/snippet），再由你基于 id 或标题继续处理。"
            "若只是当前回合一次性输出且无需沉淀，不应调用本工具。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索关键词或自然语言意图（例如“上次的招聘海报文案”）。",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "返回候选数量上限（1-20）。数量越大，召回更全但噪音可能增加。",
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
            "将本轮结果保存为可复用产物，供后续检索、复用与迭代。"
            "适用于有“交付物”属性的输出：报告、方案、文案、脚本、页面片段等。"
            "category 用于归档分类（如“内容”“报告”）；若不存在可先调用 artifact_category_create。"
            "不用于临时解释或一次性对话回复。"
            "保存完成后，在回复中简要确认保存结果即可，无需输出链接。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "产物标题，建议可被后续检索理解。"},
                "content": {"type": "string", "description": "产物正文内容（将被持久化保存）。"},
                "type": {
                    "type": "string",
                    "enum": ["markdown", "latex", "html", "text"],
                    "description": (
                        "渲染类型：markdown=Markdown（标题/列表/代码块，不含公式）；"
                        "latex=LaTeX 公式（行内 $...$，块级 $$...$$）；"
                        "html=HTML 页面；text=纯文本。"
                        "含数学公式时必须设为 latex，不要用 markdown 或 text。"
                        "JSON 参数里反斜杠须双重转义（\\\\begin）。"
                    ),
                },
                "category": {
                    "type": "string",
                    "description": "归档类目名（如“内容”“报告”）。须已存在或先 artifact_category_create。",
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
            "按 id 更新已有产物。id 来自 artifact_recall。"
            "至少提供 title、content、category 之一；category 为类目名。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "产物 id（artifact_recall 返回的 id=...）。",
                },
                "title": {"type": "string", "description": "新标题。"},
                "content": {"type": "string", "description": "新正文。"},
                "category": {
                    "type": "string",
                    "description": "移动到的类目名（须已存在）。",
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
        description="按 id 删除产物。id 来自 artifact_recall。",
        parameters={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "产物 id（artifact_recall 返回的 id=...）。",
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
        description="按 id 读取产物全文。id 来自 artifact_recall 或 artifact_list。",
        parameters={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "产物 id（artifact_recall / artifact_list 返回的 id=...）。",
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
        description="按类目列出产物条目（id/title/type）。类目可用 category 名或 category_id。",
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "类目名。"},
                "category_id": {"type": "string", "description": "类目 id。"},
                "limit": {"type": "integer", "default": 50, "description": "返回条数上限（1-200）。"},
            },
            "additionalProperties": False,
        },
        handler=_artifact_list,
    )
)


register_builtin(
    Tool(
        name="artifact_category_update",
        description="更新产物类目名称或描述。按 category_id 或 category 定位。",
        parameters={
            "type": "object",
            "properties": {
                "category_id": {"type": "string", "description": "类目 id。"},
                "category": {"type": "string", "description": "类目名（id 未知时）。"},
                "name": {"type": "string", "description": "新类目名。"},
                "description": {"type": "string", "description": "新描述。"},
            },
            "additionalProperties": False,
        },
        handler=_artifact_category_update,
    )
)


register_builtin(
    Tool(
        name="artifact_category_delete",
        description="删除产物类目及其下全部产物。按 category_id 或 category 定位。",
        parameters={
            "type": "object",
            "properties": {
                "category_id": {"type": "string", "description": "类目 id。"},
                "category": {"type": "string", "description": "类目名（id 未知时）。"},
            },
            "additionalProperties": False,
        },
        handler=_artifact_category_delete,
    )
)
