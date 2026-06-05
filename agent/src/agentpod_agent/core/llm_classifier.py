"""共享 LLM JSON 分类器：用于意图/路由类决策（非分词规则）。"""

from __future__ import annotations

import json
from typing import Any

from ..logging import get_logger
from .auxiliary_completion import create_chat_completion
from .llm import get_llm_client
from .models import ModelRole, resolve_model
from .openai_fields import openai_completion_text
from ..usage_report import schedule_openai_usage

log = get_logger("llm_classifier")


def parse_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty response")
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("response must be a JSON object")
    return parsed


async def classify_json(
    *,
    system_prompt: str,
    user_content: str,
    scenario: str,
    session_id: str | None = None,
    model_role: ModelRole = "compression",
    max_tokens: int = 128,
    temperature: float = 0.0,
    retry_log_event: str = "llm_classifier_disable_thinking_retry",
) -> dict[str, Any]:
    text = str(user_content or "").strip()
    if not text:
        return {}

    model = await resolve_model(model_role)
    resp = await create_chat_completion(
        get_llm_client(),
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text[:4000]},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        retry_log_event=retry_log_event,
    )
    schedule_openai_usage(
        usage=resp.usage,
        scenario=scenario,
        model=model,
        session_id=session_id,
    )
    return parse_json_object(openai_completion_text(resp))
