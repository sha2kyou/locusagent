"""向用户容器代理请求：流式无缓冲、注入 X-Internal-Token、过滤敏感头。

约束：
- 状态非 running 时按状态机分支处理（503/500/恢复后转发）。
- 不透传 Authorization / Cookie 给容器，避免泄漏宿主鉴权信息。
- 流式响应通过 StreamingResponse 全程不缓冲，SSE 头由容器返回时透传。
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..config import get_settings
from ..db import ContainerStatus, User
from ..logging import get_logger
from ..orchestrator import container_name_for, ensure_container_ready, reconcile_container_state, touch_last_active
from ..security import decrypt_str

log = get_logger("proxy")

AGENT_PORT = 8000

HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "authorization",
    "cookie",
}


def _filter_request_headers(src: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in src.items() if k.lower() not in HOP_HEADERS}


def _filter_response_headers(src: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in src.items() if k.lower() not in HOP_HEADERS}


async def proxy_to_user_container(
    request: Request,
    user: User,
    target_path: str,
    *,
    method: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    settings = get_settings()
    state, _meta = await ensure_container_ready(user.id)

    if state == ContainerStatus.CREATING:
        return JSONResponse(
            {"error": {"code": "starting", "message": "container is starting"}},
            status_code=503,
            headers={
                "Retry-After": "5",
                "X-Container-State": "starting",
            },
        )
    if state != ContainerStatus.RUNNING:
        return JSONResponse(
            {"error": {"code": "unavailable", "message": f"container state={state.value}"}},
            status_code=503,
            headers={"Retry-After": "5", "X-Container-State": state.value},
        )

    if user.internal_token_enc is None:
        return JSONResponse(
            {"error": {"code": "missing_internal_token", "message": "internal token missing"}},
            status_code=500,
        )
    internal_token = decrypt_str(user.internal_token_enc)

    container_host = container_name_for(user.id)
    target_url = f"http://{container_host}:{AGENT_PORT}{target_path}"

    method = (method or request.method).upper()
    raw_headers = _filter_request_headers(dict(request.headers))
    raw_headers["X-Internal-Token"] = internal_token
    raw_headers["X-User-Id"] = str(user.id)
    if extra_headers:
        raw_headers.update(extra_headers)

    body = await request.body()

    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=None, write=30.0, pool=5.0))
    try:
        req = client.build_request(
            method,
            target_url,
            params=request.query_params,
            headers=raw_headers,
            content=body if body else None,
        )
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        log.warning("proxy_upstream_failed", user_id=user.id, target=target_path, error=str(exc))
        try:
            await reconcile_container_state(user.id)
        except Exception as reconcile_exc:
            log.warning("proxy_reconcile_failed", user_id=user.id, error=str(reconcile_exc))
        return JSONResponse(
            {"error": {"code": "upstream_error", "message": str(exc)}},
            status_code=503,
            headers={"Retry-After": "3", "X-Container-State": "error"},
        )

    is_sse = upstream.headers.get("content-type", "").startswith("text/event-stream")
    response_headers = _filter_response_headers(upstream.headers)
    if is_sse:
        response_headers.setdefault("Cache-Control", "no-cache")
        response_headers.setdefault("X-Accel-Buffering", "no")

    async def _stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    log.info(
        "proxy_forwarded",
        user_id=user.id,
        method=method,
        target=target_path,
        status=upstream.status_code,
        sse=is_sse,
    )
    try:
        await touch_last_active(user.id)
    except Exception as exc:
        log.warning("touch_last_active_failed", user_id=user.id, error=str(exc))
    return StreamingResponse(
        _stream(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
