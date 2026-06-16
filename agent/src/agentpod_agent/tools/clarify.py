"""clarify 工具：向用户发起单选澄清问题。

不产生真实副作用：把 question/choices 原样回吐为结果，前端渲染为单选选项卡片；
调用后 agent 应结束本轮回复，等待用户选定一项作为下一条用户消息。
"""

from __future__ import annotations

import json
from typing import Any

from .base import Tool, ToolError, ToolResult, register_builtin


def is_clarify_result(content: str) -> bool:
    """工具返回是否为可渲染的单选 clarify 卡片。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict) or not isinstance(data.get("question"), str):
        return False
    choices = data.get("choices")
    if not isinstance(choices, list):
        return False
    return len([c for c in choices if str(c).strip()]) >= 2


async def _clarify(args: dict[str, Any]) -> ToolResult:
    question = str(args.get("question", "")).strip()
    if not question:
        raise ToolError("question is required")

    choices_raw = args.get("choices")
    if choices_raw is None:
        raise ToolError(
            "choices is required: pass 2–4 mutually exclusive options in choices "
            "(do not list options only in question)"
        )
    if not isinstance(choices_raw, list):
        raise ToolError("choices must be an array")
    choices = [str(o).strip() for o in choices_raw if str(o).strip()]
    if len(choices) < 2:
        raise ToolError("choices must contain at least 2 non-empty options")
    if len(choices) > 4:
        choices = choices[:4]

    allow_other = bool(args.get("allow_other", True))
    payload = {"question": question, "choices": choices, "allow_other": allow_other}
    return ToolResult(content=json.dumps(payload, ensure_ascii=False), metadata={"clarify": True})


register_builtin(
    Tool(
        name="clarify",
        strict_schema=True,
        description=(
            "Purpose: ask the user a single-select clarification when you need feedback or a decision. "
            "Provide 2–4 mutually exclusive choices; the user picks one, or may enter a custom option via Other. "
            "Use when: "
            "- the task is ambiguous and the user must pick a direction; "
            "- you need post-task feedback (e.g. how did it work?); "
            "- the decision involves important tradeoffs for the user. "
            "Do not use when: "
            "- the user must select multiple items; "
            "- a simple yes/no suffices; "
            "- answers cannot be enumerated (pick a reasonable default instead); "
            "- low-stakes decisions where you should decide yourself. "
            "Parameters: "
            "- question (required): concise question—do not list options in question; "
            "- choices (required): 2–4 mutually exclusive options, single-select; "
            "- allow_other (required): allow free-text Other; usually true."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Clarification question for the user (no option list in question)",
                },
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 4,
                    "description": "Mutually exclusive options (2–4); user selects one",
                },
                "allow_other": {
                    "type": "boolean",
                    "description": "Whether to allow free-text Other; usually true",
                },
            },
            "required": ["question", "choices", "allow_other"],
            "additionalProperties": False,
        },
        handler=_clarify,
    )
)
