"""工作区 API 转发：Session 鉴权 → Agent /workspace/*。

Host 不直接写工作区数据，CRUD 经内部 HTTP 转发到 Agent。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import AuthContext, require_session
from ..proxy import proxy_to_agent

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

PROXY_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]


@router.api_route("/skills", methods=PROXY_METHODS)
@router.api_route("/skills/install", methods=["POST"])
@router.api_route("/skills/{name}/files", methods=["GET"])
@router.api_route("/skills/{name}/file", methods=["GET"])
@router.api_route("/skills/{name}", methods=PROXY_METHODS)
async def proxy_skills(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    name: str | None = None,
):
    path = request.url.path.rstrip("/")
    if path.endswith("/install"):
        target = "/workspace/skills/install"
    elif name and path.endswith("/files"):
        target = f"/workspace/skills/{name}/files"
    elif name and path.endswith("/file"):
        target = f"/workspace/skills/{name}/file"
    elif name:
        target = f"/workspace/skills/{name}"
    else:
        target = "/workspace/skills"
    return await proxy_to_agent(request, target)


@router.api_route("/mcp", methods=PROXY_METHODS)
@router.api_route("/mcp/{name}", methods=PROXY_METHODS)
async def proxy_mcp(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    name: str | None = None,
):
    target = f"/workspace/mcp/{name}" if name else "/workspace/mcp"
    return await proxy_to_agent(request, target)


@router.api_route("/tools", methods=PROXY_METHODS)
@router.api_route("/tools/builtin/{name}", methods=PROXY_METHODS)
async def proxy_tools(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    name: str | None = None,
):
    target = f"/workspace/tools/builtin/{name}" if name else "/workspace/tools"
    return await proxy_to_agent(request, target)


@router.api_route("/memory", methods=PROXY_METHODS)
@router.api_route("/memory/{entry_id}", methods=PROXY_METHODS)
async def proxy_memory(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    entry_id: int | None = None,
):
    target = f"/workspace/memory/{entry_id}" if entry_id is not None else "/workspace/memory"
    return await proxy_to_agent(request, target)


@router.api_route("/env-vars", methods=PROXY_METHODS)
@router.post("/env-vars/recall")
@router.api_route("/env-vars/{entry_id}", methods=PROXY_METHODS)
async def proxy_env_vars(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    entry_id: int | None = None,
):
    path = request.url.path.rstrip("/")
    if path.endswith("/recall"):
        target = "/workspace/env-vars/recall"
    elif entry_id is not None:
        target = f"/workspace/env-vars/{entry_id}"
    else:
        target = "/workspace/env-vars"
    return await proxy_to_agent(request, target)


@router.api_route("/sessions", methods=PROXY_METHODS)
@router.get("/sessions/{session_id}/active-run")
@router.get("/sessions/{session_id}/runs/{run_id}/stream")
@router.api_route("/sessions/{session_id}", methods=PROXY_METHODS)
async def proxy_sessions(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    session_id: str | None = None,
    run_id: str | None = None,
):
    path = request.url.path.rstrip("/")
    if path.endswith("/active-run") and session_id:
        target = f"/workspace/sessions/{session_id}/active-run"
    elif run_id and session_id and "/runs/" in path and path.endswith("/stream"):
        target = f"/workspace/sessions/{session_id}/runs/{run_id}/stream"
    elif session_id is not None:
        target = f"/workspace/sessions/{session_id}"
    else:
        target = "/workspace/sessions"
    return await proxy_to_agent(request, target)


@router.post("/sessions/{session_id}/cancel")
async def cancel_session_run(
    request: Request,
    session_id: str,
    ctx: AuthContext = Depends(require_session),
):
    """按 session 粒度取消运行中的任务。"""
    return await proxy_to_agent(request, f"/workspace/sessions/{session_id}/cancel")


@router.api_route("/artifact-categories", methods=PROXY_METHODS)
@router.api_route("/artifact-categories/{category_id}", methods=PROXY_METHODS)
async def proxy_artifact_categories(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    category_id: str | None = None,
):
    target = (
        f"/workspace/artifact-categories/{category_id}"
        if category_id
        else "/workspace/artifact-categories"
    )
    return await proxy_to_agent(request, target)


@router.api_route("/artifacts", methods=PROXY_METHODS)
@router.api_route("/artifacts/{artifact_id}", methods=PROXY_METHODS)
async def proxy_artifacts(
    request: Request,
    ctx: AuthContext = Depends(require_session),
    artifact_id: str | None = None,
):
    target = f"/workspace/artifacts/{artifact_id}" if artifact_id else "/workspace/artifacts"
    return await proxy_to_agent(request, target)


@router.get("/attachments/{attachment_id}/download")
async def proxy_attachment_download(
    request: Request,
    attachment_id: str,
    ctx: AuthContext = Depends(require_session),
):
    return await proxy_to_agent(
        request,
        f"/workspace/attachments/{attachment_id}/download",
    )


@router.api_route("/attachments", methods=PROXY_METHODS)
async def proxy_attachments(
    request: Request,
    ctx: AuthContext = Depends(require_session),
):
    return await proxy_to_agent(request, "/workspace/attachments")


@router.post("/chat/completions")
async def proxy_chat_for_web(
    request: Request,
    ctx: AuthContext = Depends(require_session),
):
    """前端 Chat 页专用：session 鉴权代理到 Agent /v1/chat/completions。

    避免与对外 API 路径白名单冲突；同时保持 session 与 bearer 互斥。
    """
    return await proxy_to_agent(request, "/v1/chat/completions")
