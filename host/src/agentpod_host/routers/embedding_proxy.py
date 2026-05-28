"""Agent 容器 embedding 代理：用户隔离网络不可直达 TEI，经宿主转发。"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..db import User
from ..logging import get_logger

router = APIRouter(prefix="/internal/embedding", tags=["embedding-proxy"])
log = get_logger("embedding_proxy")


@router.post("/v1/embeddings")
async def proxy_embeddings(
    request: Request,
    user: User = Depends(require_agent_internal),
) -> Response:
    settings = get_settings()
    body = await request.body()
    url = f"{settings.embedding_base_url.rstrip('/')}/v1/embeddings"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=2.0, read=30.0, write=5.0, pool=5.0)
    ) as client:
        resp = await client.post(
            url,
            content=body,
            headers={"Content-Type": request.headers.get("content-type", "application/json")},
        )
    log.info("embedding_proxied", user_id=user.id, status=resp.status_code)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
