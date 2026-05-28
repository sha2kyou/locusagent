"""工作区管理转发：Session 鉴权 → 容器 /workspace/*。

V1 唯一写入路径：宿主**不直接写**用户 volume，所有 CRUD 转发到容器 API。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import AuthContext, require_session
from ..proxy import proxy_to_user_container

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

PROXY_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]


@router.api_route("/skills", methods=PROXY_METHODS)
@router.api_route("/skills/{name}", methods=PROXY_METHODS)
async def proxy_skills(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    name: str | None = None,
):
    target = f"/workspace/skills/{name}" if name else "/workspace/skills"
    return await proxy_to_user_container(request, ctx.user, target)


@router.api_route("/mcp", methods=PROXY_METHODS)
@router.api_route("/mcp/{name}", methods=PROXY_METHODS)
async def proxy_mcp(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    name: str | None = None,
):
    target = f"/workspace/mcp/{name}" if name else "/workspace/mcp"
    return await proxy_to_user_container(request, ctx.user, target)


@router.api_route("/memory", methods=PROXY_METHODS)
@router.api_route("/memory/{entry_id}", methods=PROXY_METHODS)
async def proxy_memory(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    entry_id: int | None = None,
):
    target = f"/workspace/memory/{entry_id}" if entry_id is not None else "/workspace/memory"
    return await proxy_to_user_container(request, ctx.user, target)


@router.api_route("/sessions", methods=PROXY_METHODS)
@router.get("/sessions/{session_id}/active-run")
@router.api_route("/sessions/{session_id}", methods=PROXY_METHODS)
async def proxy_sessions(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    session_id: str | None = None,
):
    path = request.url.path.rstrip("/")
    if path.endswith("/active-run") and session_id:
        target = f"/workspace/sessions/{session_id}/active-run"
    elif session_id is not None:
        target = f"/workspace/sessions/{session_id}"
    else:
        target = "/workspace/sessions"
    return await proxy_to_user_container(request, ctx.user, target)


@router.post("/sessions/{session_id}/cancel")
async def cancel_session_run(
    request: Request,
    session_id: str,
    ctx: AuthContext = Depends(require_session),
):
    """按 session 粒度取消运行中的任务，避免容器级 stop 造成 run 状态残留。"""
    return await proxy_to_user_container(request, ctx.user, f"/workspace/sessions/{session_id}/cancel")


@router.post("/chat/completions")
async def proxy_chat_for_web(
    request: Request,
    ctx: AuthContext = Depends(require_session),
):
    """前端 Chat 页专用：session 鉴权代理到容器 /v1/chat/completions。

    避免与对外 API 路径白名单冲突；同时保持 session 与 bearer 互斥。
    """
    return await proxy_to_user_container(request, ctx.user, "/v1/chat/completions")
