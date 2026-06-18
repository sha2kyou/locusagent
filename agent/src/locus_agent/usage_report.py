"""向 Host 上报用量（LLM token / 第三方 API）。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .config import get_settings
from .host_internal import HostInternalError, error_detail, internal_base_and_headers
from .logging import get_logger
from .workspace import get_workspace_id

log = get_logger("usage_report")

_PENDING: set[asyncio.Task[None]] = set()


def _usage_triplet(usage: Any) -> tuple[int, int, int]:
    if usage is None:
        return 0, 0, 0
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or 0)
    if total <= 0 and (prompt > 0 or completion > 0):
        total = prompt + completion
    return prompt, completion, total


def schedule_openai_usage(
    *,
    usage: Any,
    scenario: str,
    model: str,
    session_id: str | None = None,
) -> None:
    prompt, completion, total = _usage_triplet(usage)
    if total <= 0 and prompt <= 0 and completion <= 0:
        return
    schedule_usage_event(
        scenario=scenario,
        model=model,
        session_id=session_id,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def schedule_api_call(
    *,
    scenario: str,
    model: str | None = None,
    session_id: str | None = None,
    api_calls: int = 1,
    total_tokens: int = 0,
) -> None:
    if api_calls <= 0 and total_tokens <= 0:
        return
    schedule_usage_event(
        scenario=scenario,
        model=model,
        session_id=session_id,
        api_calls=max(api_calls, 0),
        total_tokens=max(total_tokens, 0),
    )


def schedule_usage_event(
    *,
    scenario: str,
    model: str | None = None,
    session_id: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    api_calls: int = 0,
) -> None:
    if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0 and api_calls <= 0:
        return
    event = {
        "scenario": scenario.strip(),
        "model": (model or "").strip() or None,
        "session_id": (session_id or "").strip() or None,
        "prompt_tokens": max(prompt_tokens, 0),
        "completion_tokens": max(completion_tokens, 0),
        "total_tokens": max(total_tokens, 0),
        "api_calls": max(api_calls, 0),
    }
    task = asyncio.create_task(_post_events([event]), name="usage-report")
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)


async def _post_events(events: list[dict[str, Any]]) -> None:
    settings = get_settings()
    if not settings.host_internal_url or not settings.internal_token:
        return
    try:
        base, headers = internal_base_and_headers(workspace_id=get_workspace_id())
    except HostInternalError:
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)) as client:
            resp = await client.post(
                f"{base}/internal/usage/events",
                headers=headers,
                json={"events": events},
            )
        if resp.status_code >= 400:
            log.warning("usage_report_failed", status=resp.status_code, detail=error_detail(resp))
    except httpx.HTTPError as exc:
        log.warning("usage_report_unreachable", error=str(exc))
