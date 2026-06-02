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
            "用途：当需要澄清、反馈或决策时向用户发起单选提问。"
            "必须提供 2–4 个互斥 choices，用户只能选其中一项；也可通过“其他”自由输入一项。"
            "适用场景："
            "- 任务不明确，需要用户选定一个方向。"
            "- 需要任务后反馈（如“效果如何？”）。"
            "- 决策涉及用户需要权衡的重要取舍。"
            "不适用场景："
            "- 需要用户同时选多项。"
            "- 简单的是/否确认。"
            "- 答案无法枚举为有限选项时（自行做合理默认，勿调用 clarify）。"
            "- 低风险决策，最好自己做出合理默认选择。"
            "参数："
            "- question（必需）：简洁的澄清问题；不要把候选项写在 question 里。"
            "- choices（必需）：2–4 个互斥候选项，用户单选其一。"
            "- allow_other（必需）：是否允许“其他”自由输入；通常为 true。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "向用户提出的澄清问题（不含候选项列表）",
                },
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 4,
                    "description": "互斥候选项（2–4 个）；用户单选其一",
                },
                "allow_other": {
                    "type": "boolean",
                    "description": "是否允许“其他”自由输入；通常为 true",
                },
            },
            "required": ["question", "choices", "allow_other"],
            "additionalProperties": False,
        },
        handler=_clarify,
    )
)
