"""Agent 容器 embedding 代理：用户隔离网络不可直达 TEI，经宿主转发。"""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..db import User
from ..internal_proxy_limits import audit_internal_proxy, enforce_internal_rate_limit
from ..logging import get_logger
from ..usage import record_usage_event

router = APIRouter(prefix="/internal/embedding", tags=["embedding-proxy"])
log = get_logger("embedding_proxy")


@router.post("/v1/embeddings")
async def proxy_embeddings(
    request: Request,
    user: User = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> Response:
    await enforce_internal_rate_limit(user_id=user.id, bucket="embedding")
    settings = get_settings()
    body = await request.body()
    embed_model = settings.embedding_model
    try:
        payload = json.loads(body) if body else {}
        if isinstance(payload, dict) and payload.get("model"):
            embed_model = str(payload["model"])
    except json.JSONDecodeError:
        pass
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
    await audit_internal_proxy(
        "proxy.embedding",
        user_id=user.id,
        detail={"status": resp.status_code},
    )
    if resp.status_code == 200:
        total_tokens = 0
        try:
            data = resp.json()
            usage = data.get("usage") if isinstance(data, dict) else None
            if isinstance(usage, dict):
                total_tokens = int(usage.get("total_tokens") or 0)
        except Exception:
            total_tokens = 0
        ws = (x_workspace_id or "").strip() or None
        await record_usage_event(
            user_id=user.id,
            workspace_id=ws,
            scenario="embedding",
            model=embed_model,
            total_tokens=total_tokens,
            api_calls=1,
        )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
