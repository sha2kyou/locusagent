"""clarify 工具：向用户发起澄清问题（多选或开放式）。

不产生真实副作用：把 question/choices 原样回吐为结果，前端据此渲染为选项卡片或开放输入；
调用后 agent 应结束本轮回复，等待用户的回答作为下一条用户消息。
"""

from __future__ import annotations

import json
from typing import Any

from .base import Tool, ToolError, ToolResult, register_builtin


async def _clarify(args: dict[str, Any]) -> ToolResult:
    question = str(args.get("question", "")).strip()
    if not question:
        raise ToolError("question is required")

    # 新字段是 choices；保留 options 兼容历史调用。
    choices_raw = args.get("choices", args.get("options"))
    if choices_raw is None:
        choices: list[str] = []
    else:
        if not isinstance(choices_raw, list):
            raise ToolError("choices must be an array")
        choices = [str(o).strip() for o in choices_raw if str(o).strip()]
        if len(choices) > 4:
            choices = choices[:4]

    allow_other = bool(args.get("allow_other", True))
    payload = {"question": question, "choices": choices, "allow_other": allow_other}
    return ToolResult(content=json.dumps(payload, ensure_ascii=False), metadata={"clarify": True})


register_builtin(
    Tool(
        name="clarify",
        description=(
            "用途：当需要澄清、反馈或决策时向用户提问。"
            "两种模式："
            "1. 多选模式 - 提供最多4个选项，用户可选择其中一项或通过“其他”选项自由输入。"
            "2. 开放式模式 - 不提供选项，用户自由输入回答。"
            "适用场景："
            "- 任务不明确，需要用户选择方法。"
            "- 需要任务后反馈（如“效果如何？”）。"
            "- 想要提供保存技能或更新记忆的机会。"
            "- 决策涉及用户需要权衡的重要取舍。"
            "不适用场景："
            "- 简单的是/否确认。"
            "- 低风险决策，最好自己做出合理默认选择。"
            "参数："
            "- question（必需）：要向用户提出的问题。"
            "- choices（可选）：最多4个选项的数组。省略时切换到开放式模式。"
            "特点："
            "- 用户可以通过第5个“其他”选项输入自己的答案。"
            "- 不应用于简单的是/否确认。"
            "- 低风险决策时，优先自己做合理默认选择。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "向用户提出的澄清问题"},
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                    "description": "供用户选择的候选项（最多 4 个）；省略时为开放式提问",
                },
            },
            "required": ["question"],
        },
        handler=_clarify,
    )
)
