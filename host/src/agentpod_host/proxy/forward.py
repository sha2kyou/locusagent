"""向 Agent 代理请求：流式无缓冲、注入 X-Internal-Token、过滤敏感头。"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..agent_service import agent_url, load_internal_token
from ..db import get_session
from ..logging import get_logger
from ..workspaces import requested_workspace_id, resolve_workspace

log = get_logger("proxy")

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


async def proxy_to_agent(
    request: Request,
    target_path: str,
    *,
    method: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    workspace_id = requested_workspace_id(request)
    async with get_session() as session:
        workspace = await resolve_workspace(
            session,
            workspace_id=workspace_id,
        )

    internal_token = await load_internal_token()
    if internal_token is None:
        return JSONResponse(
            {"error": {"code": "missing_internal_token", "message": "internal token missing"}},
            status_code=500,
        )

    target_url = agent_url(target_path)

    method = (method or request.method).upper()
    raw_headers = _filter_request_headers(dict(request.headers))
    raw_headers["X-Internal-Token"] = internal_token
    raw_headers["X-Workspace-Id"] = workspace.id
    if extra_headers:
        raw_headers.update(extra_headers)

    body = await request.body()

    accept = request.headers.get("accept", "")
    is_sse_request = accept.startswith("text/event-stream")
    read_timeout = None if is_sse_request else 120.0
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=read_timeout, write=30.0, pool=5.0),
    )
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
        log.warning("proxy_upstream_failed", target=target_path, error=str(exc))
        return JSONResponse(
            {"error": {"code": "upstream_error", "message": str(exc)}},
            status_code=503,
            headers={"Retry-After": "3"},
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
        method=method,
        target=target_path,
        status=upstream.status_code,
        sse=is_sse,
    )
    return StreamingResponse(
        _stream(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
