"""Agent embedding：桌面内嵌 fastembed 小模型。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from ..auth.agent_internal import require_agent_internal
from ..config import get_settings
from ..internal_proxy_limits import enforce_internal_rate_limit
from ..logging import get_logger
from ..usage import record_usage_event

router = APIRouter(prefix="/internal/embedding", tags=["embedding-proxy"])
log = get_logger("embedding_proxy")


@router.post("/v1/embeddings")
async def proxy_embeddings(
    request: Request,
    _auth: None = Depends(require_agent_internal),
    x_workspace_id: str = Header(default="", alias="X-Workspace-Id"),
) -> JSONResponse:
    ws = (x_workspace_id or "").strip() or None
    await enforce_internal_rate_limit(bucket="embedding", workspace_id=ws)
    settings = get_settings()
    body = await request.body()
    embed_model = settings.embedding_model
    try:
        payload = json.loads(body) if body else {}
        if isinstance(payload, dict) and payload.get("model"):
            embed_model = str(payload["model"])
    except json.JSONDecodeError:
        pass

    from agentpod_shared.local_embeddings import embed_openai_response_from_body

    try:
        data, total_tokens = await embed_openai_response_from_body(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.warning("embedding_local_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="embedding unavailable") from exc

    log.info("embedding_local", model=embed_model)
    await record_usage_event(
        workspace_id=ws,
        scenario="embedding",
        model=embed_model,
        total_tokens=total_tokens,
        api_calls=1,
    )
    return JSONResponse(content=data)
