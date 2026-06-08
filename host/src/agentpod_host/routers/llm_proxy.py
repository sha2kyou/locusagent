"""Agent 容器 LLM 代理：平台 API Key 仅留在 Host，容器用 Internal Token 鉴权。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..internal_proxy_headers import forward_headers_to_upstream
from ..internal_proxy_limits import enforce_internal_rate_limit
from ..llm_proxy_paths import assert_llm_proxy_path_allowed
from ..llm_url import upstream_url_for_proxy_path
from ..logging import get_logger

router = APIRouter(prefix="/internal/llm", tags=["llm-proxy"])
log = get_logger("llm_proxy")

_HOP_RESPONSE = frozenset(
    {
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
        "content-encoding",
    }
)


def _request_streams(body: bytes) -> bool:
    if not body:
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    return bool(payload.get("stream"))


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_llm(
    path: str,
    request: Request,
    _auth: None = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> Response:
    try:
        assert_llm_proxy_path_allowed(path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    ws = (x_workspace_id or "").strip() or None
    await enforce_internal_rate_limit(bucket="llm", workspace_id=ws)
    settings = get_settings()
    if not settings.llm_api_key.strip():
        return Response(
            content='{"error":{"message":"LLM_API_KEY not configured on host"}}',
            status_code=503,
            media_type="application/json",
        )

    try:
        upstream = upstream_url_for_proxy_path(llm_base_url=settings.llm_base_url, path=path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    body = await request.body()
    headers = forward_headers_to_upstream(
        request,
        authorization=f"Bearer {settings.llm_api_key}",
    )
    timeout = httpx.Timeout(connect=5.0, read=600.0, write=30.0, pool=5.0)
    stream = _request_streams(body)

    if stream:
        client = httpx.AsyncClient(timeout=timeout)
        req = client.build_request(
            request.method,
            upstream,
            headers=headers,
            content=body if body else None,
        )
        try:
            resp = await client.send(req, stream=True)
        except httpx.HTTPError as exc:
            await client.aclose()
            log.warning("llm_proxy_stream_failed", error=str(exc))
            return Response(
                content='{"error":{"message":"upstream llm unreachable"}}',
                status_code=502,
                media_type="application/json",
            )

        async def _iter() -> AsyncIterator[bytes]:
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        out_headers = {
            k: v for k, v in resp.headers.items() if k.lower() not in _HOP_RESPONSE
        }
        log.info("llm_proxied_stream", path=path, status=resp.status_code)
        return StreamingResponse(
            _iter(),
            status_code=resp.status_code,
            headers=out_headers,
            media_type=resp.headers.get("content-type"),
        )

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.request(
                request.method,
                upstream,
                headers=headers,
                content=body if body else None,
            )
        except httpx.HTTPError as exc:
            log.warning("llm_proxy_failed", error=str(exc))
            return Response(
                content='{"error":{"message":"upstream llm unreachable"}}',
                status_code=502,
                media_type="application/json",
            )

    log.info("llm_proxied", path=path, status=resp.status_code)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
