"""产物工具：artifact_save 归档产出，artifact_recall 按标题语义召回。

类目按名匹配；不存在时自动创建，对应前端「产物」下的一个子菜单。
"""

from __future__ import annotations

import re
from typing import Any

from ..artifacts import (
    create_artifact,
    create_category,
    recall_artifacts,
    resolve_category_id,
)
from .base import Tool, ToolError, ToolResult, register_builtin

_HTML_RENDER_RE = re.compile(r"\[HTML_RENDER\]([\s\S]*?)\[/HTML_RENDER\]", re.IGNORECASE)


async def _artifact_save(args: dict[str, Any]) -> ToolResult:
    title = str(args.get("title", "")).strip()
    content = str(args.get("content", ""))
    category = str(args.get("category", "")).strip()
    art_type = str(args.get("type", "markdown")).strip().lower() or "markdown"
    if not title:
        raise ToolError("title is required")
    if not content.strip():
        raise ToolError("content is required")

    # html-render 输出的可视化带 [HTML_RENDER] 包裹：剥离标记取内部 HTML，按 html 类型保存
    m = _HTML_RENDER_RE.search(content)
    if m:
        content = m.group(1).strip()
        art_type = "html"

    category_id: str | None = None
    if category:
        category_id = await resolve_category_id(category)
        if category_id is None:
            created = await create_category(category)
            category_id = str(created["id"])

    art = await create_artifact(
        title=title, content=content, type=art_type, category_id=category_id
    )
    suffix = f"（类目：{category}）" if category else "（未分类）"
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


register_builtin(
    Tool(
        name="artifact_recall",
        description=(
            "按标题语义检索已保存的「产物」。当用户提到之前产出过的成果（报告/图表/代码/文案等）、"
            "想找回或基于既有产物继续时调用，返回匹配产物的标题、类型、id 与摘要。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索意图/关键词"},
                "top_k": {"type": "integer", "default": 5, "description": "返回数量上限（1-20）"},
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
            "将本轮产出保存为「产物」，供用户在产物菜单中查看。"
            "仅在用户明确要求产出某类成果（如创建广告、生成报告等）时调用。"
            "category 为产物类目名（即产物下的子菜单，如「广告」「报告」），不存在会自动创建。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "产物标题"},
                "content": {"type": "string", "description": "产物正文"},
                "type": {
                    "type": "string",
                    "enum": ["markdown", "html", "text"],
                    "description": "正文类型，决定渲染方式：markdown（默认）/html/text",
                },
                "category": {
                    "type": "string",
                    "description": "类目名（子菜单），如「广告」「报告」；可留空表示未分类",
                },
            },
            "required": ["title", "content"],
        },
        handler=_artifact_save,
    )
)
