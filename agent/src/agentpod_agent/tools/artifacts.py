"""产物工具：保存、召回与类目创建。"""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from ..artifacts import (
    create_artifact,
    create_category,
    list_categories,
    recall_artifacts,
    resolve_category_id,
)
from .base import Tool, ToolError, ToolResult, register_builtin

_HTML_RENDER_RE = re.compile(r"\[HTML_RENDER\]([\s\S]*?)\[/HTML_RENDER\]", re.IGNORECASE)
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

    # html-render 输出的可视化带 [HTML_RENDER] 包裹：剥离标记取内部 HTML，按 html 类型保存
    m = _HTML_RENDER_RE.search(content)
    if m:
        content = m.group(1).strip()
        art_type = "html"

    category_id: str | None = None
    if category:
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
                    "description": "归档类目名（如“内容”“报告”）。为空则保存到未分类。",
                },
            },
            "required": ["title", "content"],
        },
        handler=_artifact_save,
    )
)
