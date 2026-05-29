"""clarify 工具：向用户呈现有限选项以消歧/决策。

不产生真实副作用：把 question/options 原样回吐为结果，前端据此渲染为可点击选项；
调用后 agent 应结束本轮回复，等待用户的选择作为下一条用户消息。
"""

from __future__ import annotations

import json
from typing import Any

from .base import Tool, ToolError, ToolResult, register_builtin


async def _clarify(args: dict[str, Any]) -> ToolResult:
    question = str(args.get("question", "")).strip()
    options_raw = args.get("options")
    if not question:
        raise ToolError("question is required")
    if not isinstance(options_raw, list):
        raise ToolError("options must be an array")
    options = [str(o).strip() for o in options_raw if str(o).strip()]
    if len(options) < 2:
        raise ToolError("options must contain at least 2 non-empty items")
    options = options[:3]
    allow_other = bool(args.get("allow_other", True))
    payload = {"question": question, "options": options, "allow_other": allow_other}
    return ToolResult(content=json.dumps(payload, ensure_ascii=False), metadata={"clarify": True})


register_builtin(
    Tool(
        name="clarify",
        description=(
            "向用户提供有限选项以澄清意图或做出决策。"
            "当请求存在多个合理解读、或某个方向/偏好会显著影响产出（如命名、设计风格、范围、技术选型）时，"
            "优先调用本工具先问清方向，而非自行假设或直接罗列所有可能。即使是“给我几个建议”这类开放式请求也适用。"
            "options 为 2~3 个简短候选（最多 3 个，不含自由输入）；allow_other 表示是否允许用户不选预设项而自由输入（默认 true）。"
            "一次只问一个问题：每轮最多调用一次，不要并行多次调用；需要多处澄清时分多轮逐个进行。"
            "调用本工具后立即结束本轮回复、不要再输出任何文字，等待用户的选择作为下一条消息。"
            "仅当任何合理选择都无差别、或用户明确要求直接给出时才跳过。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "向用户提出的澄清问题"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 3,
                    "description": "供用户选择的简短互斥候选项（最多 3 个）",
                },
                "allow_other": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否允许用户不选预设项而自由输入",
                },
            },
            "required": ["question", "options"],
        },
        handler=_clarify,
    )
)
