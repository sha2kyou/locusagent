"""对外 API：OpenAI 兼容（Bearer 鉴权）。

路径白名单：仅 /api/v1/{chat/completions, responses, models, health}。
冷启动期间返回 503 + Retry-After（不阻塞）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import AuthContext, require_bearer
from ..proxy import proxy_to_user_container

router = APIRouter(prefix="/api/v1", tags=["api"])


@router.get("/health")
async def public_health() -> dict:
    """无需鉴权的对外探活。"""
    return {"status": "ok"}


@router.post("/chat/completions")
async def chat_completions(request: Request, ctx: AuthContext = Depends(require_bearer)):
    return await proxy_to_user_container(request, ctx.user, "/v1/chat/completions")


@router.post("/responses")
async def responses(request: Request, ctx: AuthContext = Depends(require_bearer)):
    return await proxy_to_user_container(request, ctx.user, "/v1/responses")


@router.get("/responses/{response_id}")
async def retrieve_response(
    response_id: str,
    request: Request,
    ctx: AuthContext = Depends(require_bearer),
):
    return await proxy_to_user_container(request, ctx.user, f"/v1/responses/{response_id}")


@router.get("/models")
async def list_models(request: Request, ctx: AuthContext = Depends(require_bearer)):
    return await proxy_to_user_container(request, ctx.user, "/v1/models")
