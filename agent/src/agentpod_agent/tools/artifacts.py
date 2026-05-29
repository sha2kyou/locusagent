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
            "category 用于归档分类（如“广告”“报告”）；不存在时自动创建。"
            "不用于临时解释或一次性对话回复。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "产物标题，建议可被后续检索理解。"},
                "content": {"type": "string", "description": "产物正文内容（将被持久化保存）。"},
                "type": {
                    "type": "string",
                    "enum": ["markdown", "html", "text"],
                    "description": "渲染类型：markdown/html/text。省略时默认 markdown。",
                },
                "category": {
                    "type": "string",
                    "description": "归档类目名（如“广告”“报告”）。为空则保存到未分类。",
                },
            },
            "required": ["title", "content"],
        },
        handler=_artifact_save,
    )
)
