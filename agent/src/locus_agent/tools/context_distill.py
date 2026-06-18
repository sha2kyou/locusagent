"""summarize 工具：将长文本压缩为可继续工作的摘要。"""

from __future__ import annotations

from typing import Any

from ..core.completion_limits import MIN_AUXILIARY_COMPLETION_TOKENS
from .base import Tool, ToolError, ToolResult, register_builtin

_DISTILL_SYSTEM_PROMPT = (
    "You are a conversation compressor. Distill input into bullet highlights. "
    "Keep: user goals, settled conclusions, key facts/data, open items. "
    "Drop small talk and repetition. English, bullets, concise."
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

    model = await resolve_model("compression")
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
            "Summarize/compress long text into points to continue the task."
            "When context is too long or redundant and you need a stage summary first."
            "Output appears as tool result in the chat stream."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Raw text to distill."},
                "max_tokens": {
                    "type": "integer",
                    "default": MIN_AUXILIARY_COMPLETION_TOKENS,
                    "description": "Min summary completion budget 4096 (includes reasoning model thinking).",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=_summarize,
    )
)

