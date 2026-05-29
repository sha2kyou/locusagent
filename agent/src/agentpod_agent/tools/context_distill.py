"""summarize 工具：将长文本压缩为可继续工作的摘要。"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from .base import Tool, ToolError, ToolResult, register_builtin

_DISTILL_SYSTEM_PROMPT = (
    "你是对话压缩器。把输入内容浓缩成要点摘要，"
    "保留：用户目标、已确定结论、关键事实/数据、未完成事项。"
    "丢弃寒暄与重复。简体中文，分条，尽量精简。"
)


async def _summarize(args: dict[str, Any]) -> ToolResult:
    text = str(args.get("text", "")).strip()
    if not text:
        raise ToolError("text is required")
    max_tokens = int(args.get("max_tokens", 500) or 500)
    if max_tokens < 64:
        max_tokens = 64
    if max_tokens > 1500:
        max_tokens = 1500

    # 延迟导入，避免 tools 初始化阶段与 core.loop 互相导入造成循环依赖。
    from ..core.llm import get_llm_client

    settings = get_settings()
    client = get_llm_client()
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": _DISTILL_SYSTEM_PROMPT},
            {"role": "user", "content": text[:16000]},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    summary = ((resp.choices or [None])[0].message.content if resp.choices else "") or ""
    summary = summary.strip()
    if not summary:
        summary = "(empty summary)"
    return ToolResult(content=summary, metadata={"distilled": True})


register_builtin(
    Tool(
        name="summarize",
        description=(
            "对长文本进行摘要压缩，输出可继续执行任务的要点。"
            "适用于上下文过长、信息冗余、需要在继续前先做阶段总结。"
            "触发后结果会作为工具输出展示在前端消息流。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "需要蒸馏的原始文本内容。"},
                "max_tokens": {
                    "type": "integer",
                    "default": 500,
                    "description": "摘要输出长度上限（64-1500）。",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=_summarize,
    )
)

