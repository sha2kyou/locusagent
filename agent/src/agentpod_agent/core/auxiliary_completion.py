"""辅助 LLM 补全：统一 max_tokens 下限与关闭 reasoning/thinking。"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger
from .completion_limits import MIN_AUXILIARY_COMPLETION_TOKENS

log = get_logger("auxiliary_completion")

# Qwen / mimo（vLLM chat template）
_DISABLE_THINKING_EXTRA_BODY: dict[str, Any] = {
    "chat_template_kwargs": {"enable_thinking": False},
}

_NO_RETRY_STATUS = frozenset({401, 403, 408, 429, 500, 502, 503, 504})
_PARAM_RETRY_STATUS = frozenset({400, 422})
_PARAM_ERROR_KEYWORDS = (
    "reasoning",
    "thinking",
    "extra_body",
    "chat_template",
    "unsupported",
    "unknown parameter",
    "invalid",
)
_TRANSIENT_ERROR_KEYWORDS = (
    "connection",
    "timeout",
    "timed out",
    "authenticate",
    "api key",
    "unauthorized",
)


def disable_thinking_attempts() -> tuple[dict[str, Any], ...]:
    """按兼容性从高到低尝试；某一档因参数不兼容失败则换下一档。"""
    return (
        {"reasoning_effort": "none", "extra_body": _DISABLE_THINKING_EXTRA_BODY},
        {"reasoning_effort": "none"},
        {"extra_body": _DISABLE_THINKING_EXTRA_BODY},
    )


def _should_retry_disable_thinking(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is not None:
        if status in _NO_RETRY_STATUS:
            return False
        if status in _PARAM_RETRY_STATUS:
            return True
        return False
    msg = str(exc).lower()
    if any(k in msg for k in _TRANSIENT_ERROR_KEYWORDS):
        return False
    return any(k in msg for k in _PARAM_ERROR_KEYWORDS)


async def create_chat_completion(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = MIN_AUXILIARY_COMPLETION_TOKENS,
    temperature: float = 0.1,
    stream: bool = False,
    disable_thinking: bool = True,
    retry_log_event: str = "auxiliary_completion_disable_thinking_retry",
    **kwargs: Any,
) -> Any:
    base: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "max_tokens": max_tokens,
        "temperature": temperature,
        **kwargs,
    }
    attempts = disable_thinking_attempts() if disable_thinking else ({},)
    create = client.chat.completions.create
    last_exc: Exception | None = None
    for idx, extra in enumerate(attempts):
        try:
            return await create(**base, **extra)
        except Exception as exc:
            last_exc = exc
            if idx + 1 < len(attempts) and _should_retry_disable_thinking(exc):
                log.info(
                    retry_log_event,
                    model=model,
                    attempt=idx + 1,
                    error=str(exc),
                )
                continue
            raise
    assert last_exc is not None
    raise last_exc
