"""summarize 工具：将长文本压缩为可继续工作的摘要。"""

from __future__ import annotations

from typing import Any

from ..core.completion_limits import MIN_AUXILIARY_COMPLETION_TOKENS
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
    max_tokens = int(args.get("max_tokens", MIN_AUXILIARY_COMPLETION_TOKENS) or MIN_AUXILIARY_COMPLETION_TOKENS)
    if max_tokens < MIN_AUXILIARY_COMPLETION_TOKENS:
        max_tokens = MIN_AUXILIARY_COMPLETION_TOKENS

    # 延迟导入，避免 tools 初始化阶段与 core.loop 互相导入造成循环依赖。
    from ..core.llm import get_llm_client
    from ..core.openai_fields import openai_completion_text
    from ..core.models import resolve_model

    from ..core.auxiliary_completion import create_chat_completion

    model = resolve_model("compression")
    resp = await create_chat_completion(
        get_llm_client(),
        model=model,
        messages=[
            {"role": "system", "content": _DISTILL_SYSTEM_PROMPT},
            {"role": "user", "content": text[:16000]},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
        retry_log_event="summarize_disable_thinking_retry",
    )
    from ..usage_report import schedule_openai_usage

    schedule_openai_usage(usage=resp.usage, scenario="compression", model=model)
    summary = openai_completion_text(resp)
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
                    "default": MIN_AUXILIARY_COMPLETION_TOKENS,
                    "description": "摘要 completion 预算下限 4096（含推理模型 thinking）。",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=_summarize,
    )
)

