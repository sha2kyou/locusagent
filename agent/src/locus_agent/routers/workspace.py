"""Agent /workspace/* 路由：Skills / MCP / Memory / Sessions CRUD。

工作区数据写入由此处统一处理。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..auth import verify_internal_token
from ..activity import record_activity
from ..artifacts import (
    create_artifact,
    create_category,
    delete_artifact,
    delete_category,
    get_artifact,
    list_artifacts,
    list_categories,
    update_category,
    update_artifact,
)
from ..core import (
    cancel_active_run,
    create_attachment,
    delete_session,
    get_active_run,
    list_messages,
    list_sessions,
    session_lock,
)
from ..core.run_manager import (
    attach_run_subscriber,
    detach_run_subscriber,
    get_run_handle,
    reconcile_session_active_handles,
)
from ..core.run_sse import (
    build_resume_sync_payload,
    drain_subscriber_queue_nowait,
    iter_run_sse,
)
from ..core.persistence import get_attachment_download
from ..db import run_in_thread
from ..embedding_progress import get_embedding_progress
from ..env_vars import (
    add_env_var,
    delete_env_var,
    list_env_vars,
    recall_env_vars,
    update_env_var,
)
from ..errors import WsError
from ..core.run_manager import reconcile_session_active_handles
from ..host_mcp_oauth import fetch_oauth_status
from ..mcp_.probe import McpProbeError, build_http_mcp_config
from ..mcp_ import (
    MCPServerConfig,
    add_mcp_server,
    get_mcp_server,
    list_mcp_servers,
    remove_mcp_server,
    update_mcp_server,
)
from ..mcp_.client import (
    list_mcp_runtime,
    schedule_mcp_server_connect,
    schedule_mcp_server_refresh,
)
from ..core.write_origin import ORIGIN_MANUAL
from ..memory import (
    add_memory,
    delete_memory,
    enqueue_embedding,
    list_memories,
    update_memory,
)
from ..skills import (
    Skill,
    create_skill,
    delete_skill,
    get_skill,
    install_skill_from_url,
    list_skill_files,
    list_skills,
    read_skill_file,
    read_skill_file_preview,
    update_skill,
)
from ..skills.embeddings import reindex_skill
from ..tool_settings import (
    is_mcp_server_enabled,
    is_skill_enabled,
    set_builtin_tool_enabled,
)
from ..tools import registry as tool_registry
from ..workspace import get_workspace_id
from ..workspace_runtime import (
    disconnect_mcp_server_runtime,
    ensure_mcp_runtime,
    ensure_workspace_context,
    invalidate_mcp_runtime,
    schedule_mcp_runtime_warm,
)

router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
    dependencies=[Depends(verify_internal_token)],
)


class SkillIn(BaseModel):
    name: str
    description: str = ""
    body: str = ""


class AttachmentCreateIn(BaseModel):
    session_id: str | None = None
    name: str
    size_bytes: int = 0
    kind: Literal["text", "image", "other"]
    mime_type: str | None = None
    text_content: str | None = None
    image_data_url: str | None = None
    file_data_base64: str | None = None
    content_sha256: str | None = None
    file_sha256: str | None = None
    processable: bool = True
    unsupported_reason: str | None = None
    truncated: bool = False


class SkillUpdateIn(BaseModel):
    description: str | None = None
    body: str | None = None


class SkillInstallIn(BaseModel):
    url: str
    path: str | None = None
    overwrite: bool = False


@router.get("/skills")
async def workspace_list_skills() -> dict:
    skills = await run_in_thread(list_skills)
    return {
        "items": [
            {
                **s.to_dict(),
                "enabled": is_skill_enabled(s.name),
            }
            for s in skills
        ]
    }


@router.get("/skills/{name}")
async def workspace_get_skill(name: str) -> dict:
    s = await run_in_thread(get_skill, name)
    if s is None:
        raise WsError("skill_not_found", "skill not found", status_code=404)
    return s.to_dict()


@router.get("/skills/{name}/files")
async def workspace_list_skill_files(name: str) -> dict:
    s = await run_in_thread(get_skill, name)
    if s is None:
        raise WsError("skill_not_found", "skill not found", status_code=404)
    try:
        files = await run_in_thread(list_skill_files, name)
    except FileNotFoundError as exc:
        raise WsError("skill_not_found", str(exc), status_code=404) from exc
    return {"items": [entry.to_dict() for entry in files]}


@router.get("/skills/{name}/file")
async def workspace_get_skill_file(name: str, path: str = Query(..., min_length=1)) -> dict:
    s = await run_in_thread(get_skill, name)
    if s is None:
        raise WsError("skill_not_found", "skill not found", status_code=404)
    try:
        preview = await run_in_thread(read_skill_file_preview, name, path)
    except FileNotFoundError as exc:
        raise WsError("skill_file_not_found", str(exc), status_code=404) from exc
    except IsADirectoryError as exc:
        raise WsError("skill_file_invalid", str(exc), status_code=400) from exc
    except ValueError as exc:
        raise WsError("skill_file_invalid", str(exc), status_code=400) from exc
    return preview.to_dict()


@router.post("/skills/install", status_code=201)
async def workspace_install_skill(payload: SkillInstallIn) -> dict:
    try:
        result = await run_in_thread(
            install_skill_from_url,
            payload.url,
            subpath=payload.path,
            overwrite=payload.overwrite,
        )
    except FileExistsError as exc:
        raise WsError("skill_exists", str(exc), status_code=409) from exc
    except ValueError as exc:
        raise WsError("skill_install_invalid", str(exc), status_code=400) from exc
    except httpx.HTTPError as exc:
        raise WsError("skill_install_failed", f"download failed: {exc}", status_code=502) from exc
    record_activity("skill", "install", f"已安装技能「{result.name}」")
    await reindex_skill(result.name)
    return result.to_dict()


@router.post("/skills", status_code=201)
async def workspace_create_skill(payload: SkillIn) -> dict:
    skill = Skill(
        name=payload.name,
        description=payload.description,
        body=payload.body,
        source="private",
    )
    try:
        created = await run_in_thread(create_skill, skill)
    except FileExistsError as exc:
        raise WsError("skill_exists", str(exc), status_code=409) from exc
    record_activity("skill", "create", f"已创建技能「{created.name}」")
    await reindex_skill(created.name)
    return created.to_dict()


@router.put("/skills/{name}")
async def workspace_update_skill(name: str, payload: SkillUpdateIn) -> dict:
    existing = await run_in_thread(get_skill, name)
    if existing is None:
        raise WsError("skill_not_found", "skill not found", status_code=404)
    if existing.source != "private":
        raise WsError("skill_readonly", "public skill cannot be modified", status_code=403)
    try:
        updated = await run_in_thread(
            update_skill,
            name,
            description=payload.description,
            body=payload.body,
            origin=ORIGIN_MANUAL,
        )
    except ValueError as exc:
        raise WsError("skill_invalid", str(exc), status_code=400) from exc
    except FileNotFoundError as exc:
        raise WsError("skill_not_found", str(exc), status_code=404) from exc
    record_activity("skill", "update", f"已更新技能「{updated.name}」")
    await reindex_skill(updated.name)
    return updated.to_dict()


@router.delete("/skills/{name}")
async def workspace_delete_skill(name: str) -> dict:
    existing = await run_in_thread(get_skill, name)
    if existing is None:
        raise WsError("skill_not_found", "skill not found", status_code=404)
    if existing.source != "private":
        raise WsError("skill_readonly", "public skill cannot be deleted", status_code=403)
    try:
        ok = await run_in_thread(delete_skill, name)
    except ValueError as exc:
        raise WsError("skill_invalid", str(exc), status_code=400) from exc
    if not ok:
        raise WsError("skill_not_found", "private skill not found", status_code=404)
    record_activity("skill", "delete", f"已删除技能「{name}」")
    return {"deleted": True}


class MCPIn(BaseModel):
    name: str
    transport: Literal["stdio", "http"]
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    url: str | None = None


class ToolToggleIn(BaseModel):
    enabled: bool


@router.get("/tools")
async def workspace_list_tools() -> dict:
    builtins = [
        {
            "name": tool.name,
            "description": tool.description,
            "enabled": tool.enabled,
        }
        for tool in tool_registry.all()
        if tool.category == "builtin"
    ]
    builtins.sort(key=lambda t: t["name"])
    return {"builtin_tools": builtins}


@router.put("/tools/builtin/{name}")
async def workspace_toggle_builtin_tool(name: str, payload: ToolToggleIn) -> dict:
    tool = tool_registry.get(name)
    if tool is None or tool.category != "builtin":
        raise WsError("tool_not_found", "builtin tool not found", status_code=404)
    tool.enabled = payload.enabled
    await run_in_thread(set_builtin_tool_enabled, name, payload.enabled)
    record_activity(
        "tool",
        "toggle",
        f"内置工具「{name}」已{'启用' if payload.enabled else '禁用'}",
    )
    return {"name": name, "enabled": payload.enabled}


def _mcp_item_with_runtime(cfg: MCPServerConfig, runtime: dict[str, dict], *, oauth_connected: bool | None) -> dict:
    d = cfg.to_public_dict()
    r = runtime.get(cfg.name, {})
    d["enabled"] = is_mcp_server_enabled(cfg.name)
    d["connected"] = bool(r.get("connected", False))
    d["tools"] = r.get("tools", [])
    d["tool_count"] = len(d["tools"])
    if cfg.transport == "http" and cfg.auth == "oauth":
        d["oauth_required"] = True
        d["oauth_connected"] = bool(oauth_connected)
    else:
        d["oauth_required"] = False
        d["oauth_connected"] = None
    if r.get("error"):
        d["runtime_error"] = r["error"]
    if r.get("pending"):
        d["pending"] = True
    return d


def _mcp_response(cfg: MCPServerConfig, runtime: dict[str, object], *, oauth_connected: bool | None = None) -> dict:
    d = cfg.to_public_dict()
    d["enabled"] = is_mcp_server_enabled(cfg.name)
    d["connected"] = bool(runtime.get("connected", False))
    d["tools"] = runtime.get("tools", [])
    d["tool_count"] = len(d["tools"])
    if cfg.transport == "http" and cfg.auth == "oauth":
        d["oauth_required"] = True
        d["oauth_connected"] = bool(oauth_connected) if oauth_connected is not None else False
    else:
        d["oauth_required"] = False
        d["oauth_connected"] = None
    if runtime.get("error"):
        d["runtime_error"] = runtime["error"]
    if runtime.get("pending"):
        d["pending"] = True
    return d


def _set_mcp_tools_enabled(server_name: str, enabled: bool) -> None:
    from ..workspace import get_workspace_id, mcp_tool_category

    target = mcp_tool_category(server_name, get_workspace_id())
    for tool in tool_registry.all():
        if tool.category == target:
            tool.enabled = enabled


async def _build_mcp_cfg(payload: MCPIn, *, existing: MCPServerConfig | None = None) -> MCPServerConfig:
    name = payload.name.strip()
    if payload.transport == "stdio":
        return MCPServerConfig(
            name=name,
            transport="stdio",
            command=payload.command,
            args=payload.args,
            env=payload.env,
            auth="none",
        )

    url = (payload.url or "").strip()
    if not url:
        raise WsError("mcp_invalid", "http transport requires url", status_code=400)
    try:
        return await build_http_mcp_config(
            name=name,
            url=url,
            headers=dict(payload.headers),
            existing=existing,
        )
    except McpProbeError as exc:
        raise WsError("mcp_probe_failed", str(exc), status_code=400) from exc


async def _oauth_connected_map() -> set[str]:
    return await fetch_oauth_status(get_workspace_id())


@router.get("/mcp")
async def workspace_list_mcp(sync: bool = Query(False, description="为 true 时同步连接全部 MCP（较慢）")) -> dict:
    wid = get_workspace_id()
    await ensure_workspace_context(wid)
    if sync:
        await ensure_mcp_runtime(wid)
    else:
        schedule_mcp_runtime_warm(wid)
    servers, oauth_connected = await asyncio.gather(
        run_in_thread(list_mcp_servers),
        _oauth_connected_map(),
    )
    runtime = list_mcp_runtime()
    items = [
        _mcp_item_with_runtime(
            s,
            runtime,
            oauth_connected=s.name in oauth_connected if s.transport == "http" and s.auth == "oauth" else None,
        )
        for s in servers
    ]
    if sync:
        total_tools = sum(len(item.get("tools") or []) for item in items)
        connected = sum(1 for item in items if item.get("connected"))
        record_activity(
            "mcp",
            "tools_sync",
            f"同步 MCP：{len(items)} 个服务，{connected} 在线，共 {total_tools} 个工具",
            detail={"servers": [s.name for s in servers], "total_tools": total_tools},
        )
    return {"items": items}


@router.post("/mcp", status_code=201)
async def workspace_add_mcp(payload: MCPIn) -> dict:
    wid = get_workspace_id()
    cfg = await _build_mcp_cfg(payload)
    try:
        added = await run_in_thread(add_mcp_server, cfg)
    except (ValueError, FileExistsError) as exc:
        raise WsError("mcp_invalid", str(exc), status_code=400) from exc
    invalidate_mcp_runtime(wid)
    runtime = schedule_mcp_server_connect(wid, added)
    oauth_connected = added.name in await _oauth_connected_map() if added.auth == "oauth" else None
    resp = _mcp_response(added, runtime, oauth_connected=oauth_connected)
    record_activity(
        "mcp",
        "add",
        f"已添加 MCP「{added.name}」" + ("，后台连接中" if resp.get("pending") else ""),
        detail={"transport": added.transport, "pending": bool(resp.get("pending"))},
    )
    return resp


@router.put("/mcp/{name}")
async def workspace_update_mcp(name: str, payload: MCPIn) -> dict:
    existing = await run_in_thread(get_mcp_server, name)
    if existing is None:
        raise WsError("mcp_not_found", "mcp server not found", status_code=404)
    cfg = await _build_mcp_cfg(payload, existing=existing)
    try:
        updated = await run_in_thread(update_mcp_server, name, cfg)
    except FileNotFoundError as exc:
        raise WsError("mcp_not_found", str(exc), status_code=404) from exc
    except (ValueError, FileExistsError) as exc:
        raise WsError("mcp_invalid", str(exc), status_code=400) from exc
    runtime = schedule_mcp_server_refresh(get_workspace_id(), updated.name)
    enabled = is_mcp_server_enabled(updated.name)
    _set_mcp_tools_enabled(updated.name, enabled)
    oauth_connected = updated.name in await _oauth_connected_map() if updated.auth == "oauth" else None
    resp = _mcp_response(updated, runtime, oauth_connected=oauth_connected)
    record_activity("mcp", "update", f"已更新 MCP「{updated.name}」", detail={"pending": bool(resp.get("pending"))})
    return resp


@router.post("/mcp/{name}")
async def workspace_reconnect_mcp(name: str) -> dict:
    cfg = await run_in_thread(get_mcp_server, name)
    if cfg is None:
        raise WsError("mcp_not_found", "mcp server not found", status_code=404)
    runtime = schedule_mcp_server_refresh(get_workspace_id(), name)
    enabled = is_mcp_server_enabled(name)
    _set_mcp_tools_enabled(name, enabled)
    oauth_connected = cfg.name in await _oauth_connected_map() if cfg.auth == "oauth" else None
    resp = _mcp_response(cfg, runtime, oauth_connected=oauth_connected)
    record_activity("mcp", "reconnect", f"已触发 MCP 重连「{name}」", detail={"pending": bool(resp.get("pending"))})
    return resp


@router.delete("/mcp/{name}")
async def workspace_remove_mcp(name: str) -> dict:
    ok = await run_in_thread(remove_mcp_server, name)
    if not ok:
        raise WsError("mcp_not_found", "mcp server not found", status_code=404)
    await disconnect_mcp_server_runtime(get_workspace_id(), name)
    record_activity("mcp", "delete", f"已删除 MCP「{name}」")
    return {"deleted": True}


class MemoryIn(BaseModel):
    content: str
    anchor: Literal["identity", "experience"] = "experience"


class MemoryUpdateIn(BaseModel):
    content: str | None = None
    anchor: Literal["identity", "experience"] | None = None


class EnvVarIn(BaseModel):
    name: str
    value: str
    description: str = ""


class EnvVarUpdateIn(BaseModel):
    name: str | None = None
    value: str | None = None
    description: str | None = None


class EnvVarRecallIn(BaseModel):
    query: str
    top_k: int = 5


@router.get("/memory")
async def workspace_list_memory(limit: int = 100) -> dict:
    items = await list_memories(limit=limit)
    return {"items": items}


@router.post("/memory", status_code=201)
async def workspace_add_memory(payload: MemoryIn) -> dict:
    if not payload.content.strip():
        raise WsError("memory_empty", "content is empty", status_code=400)
    mid = await add_memory(payload.content, anchor=payload.anchor)
    await enqueue_embedding(mid)
    record_activity("memory", "create", f"已添加记忆 #{mid}", detail={"anchor": payload.anchor})
    return {"id": mid}


@router.put("/memory/{entry_id}")
async def workspace_update_memory(entry_id: int, payload: MemoryUpdateIn) -> dict:
    if payload.content is None and payload.anchor is None:
        raise WsError("memory_update_empty", "nothing to update", status_code=400)
    ok = await update_memory(
        entry_id,
        payload.content,
        anchor=payload.anchor,
        origin=ORIGIN_MANUAL if payload.content is not None else None,
    )
    if not ok:
        raise WsError("memory_not_found", "memory not found", status_code=404)
    if payload.content is not None:
        await enqueue_embedding(entry_id, bump=True)
    record_activity("memory", "update", f"已更新记忆 #{entry_id}")
    return {"updated": True}


@router.delete("/memory/{entry_id}")
async def workspace_delete_memory(entry_id: int) -> dict:
    ok = await delete_memory(entry_id)
    if not ok:
        raise WsError("memory_not_found", "memory not found", status_code=404)
    record_activity("memory", "delete", f"已删除记忆 #{entry_id}")
    return {"deleted": True}


@router.get("/env-vars")
async def workspace_list_env_vars(limit: int = 200) -> dict:
    items = await list_env_vars(limit=limit)
    return {"items": items}


@router.post("/env-vars", status_code=201)
async def workspace_add_env_var(payload: EnvVarIn) -> dict:
    if not payload.name.strip():
        raise WsError("env_var_name_empty", "name is empty", status_code=400)
    if not payload.value.strip():
        raise WsError("env_var_value_empty", "value is empty", status_code=400)
    try:
        env_id = await add_env_var(payload.name, payload.value, payload.description)
    except FileExistsError as exc:
        raise WsError("env_var_exists", str(exc), status_code=409) from exc
    except ValueError as exc:
        raise WsError("env_var_invalid", str(exc), status_code=400) from exc
    record_activity("env", "create", f"已添加环境变量「{payload.name.strip()}」")
    return {"id": env_id}


@router.post("/env-vars/recall")
async def workspace_recall_env_vars(payload: EnvVarRecallIn) -> dict:
    query = payload.query.strip()
    if not query:
        raise WsError("env_var_query_empty", "query is empty", status_code=400)
    items = await recall_env_vars(query, top_k=payload.top_k)
    return {"items": items}


@router.put("/env-vars/{entry_id}")
async def workspace_update_env_var(entry_id: int, payload: EnvVarUpdateIn) -> dict:
    if payload.name is None and payload.value is None and payload.description is None:
        raise WsError("env_var_update_empty", "nothing to update", status_code=400)
    try:
        ok = await update_env_var(
            entry_id,
            name=payload.name,
            value=payload.value,
            description=payload.description,
        )
    except FileExistsError as exc:
        raise WsError("env_var_exists", str(exc), status_code=409) from exc
    except ValueError as exc:
        raise WsError("env_var_invalid", str(exc), status_code=400) from exc
    if not ok:
        raise WsError("env_var_not_found", "env var not found", status_code=404)
    record_activity("env", "update", f"已更新环境变量 #{entry_id}")
    return {"updated": True}


@router.delete("/env-vars/{entry_id}")
async def workspace_delete_env_var(entry_id: int) -> dict:
    ok = await delete_env_var(entry_id)
    if not ok:
        raise WsError("env_var_not_found", "env var not found", status_code=404)
    record_activity("env", "delete", f"已删除环境变量 #{entry_id}")
    return {"deleted": True}


@router.get("/embedding-progress")
async def workspace_embedding_progress() -> dict:
    return await get_embedding_progress()


@router.get("/sessions")
async def workspace_list_sessions(limit: int = 50) -> dict:
    items = await list_sessions(limit=limit)
    return {"items": items}


@router.post("/attachments", status_code=201)
async def workspace_create_attachment(payload: AttachmentCreateIn) -> dict:
    try:
        item = await create_attachment(
            session_id=payload.session_id,
            kind=payload.kind,
            name=payload.name.strip() or "附件",
            mime_type=payload.mime_type,
            size_bytes=max(0, int(payload.size_bytes or 0)),
            text_content=payload.text_content,
            image_data_url=payload.image_data_url,
            file_data_base64=payload.file_data_base64,
            processable=bool(payload.processable),
            unsupported_reason=payload.unsupported_reason,
            truncated=bool(payload.truncated),
            content_sha256_hint=payload.content_sha256,
            file_sha256_hint=payload.file_sha256,
        )
    except ValueError as exc:
        if str(exc) == "attachment hash not found":
            raise WsError("attachment_not_found", str(exc), status_code=404) from exc
        raise WsError("attachment_invalid", str(exc), status_code=400) from exc
    return item


@router.get("/attachments/{attachment_id}/download")
async def workspace_download_attachment(attachment_id: str) -> Response:
    row = await get_attachment_download(attachment_id)
    if row is None:
        raise WsError("attachment_not_found", "attachment not found", status_code=404)
    name, _mime, data = row
    ascii_name = name.encode("ascii", "ignore").decode() or "download"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/sessions/{session_id}")
async def workspace_session_messages(session_id: str) -> dict:
    from ..todos.store import get_plan

    items = await list_messages(session_id)
    plan = await get_plan(session_id)
    return {"items": items, "todo_plan": plan}


@router.get("/sessions/{session_id}/active-run")
async def workspace_session_active_run(session_id: str) -> dict:
    await reconcile_session_active_handles(session_id)
    run = await get_active_run(session_id)
    return {"run": run}


@router.get("/sessions/{session_id}/runs/{run_id}/stream")
async def workspace_session_run_stream(session_id: str, run_id: str) -> StreamingResponse:
    await reconcile_session_active_handles(session_id)
    run = await get_active_run(session_id)
    if not run or str(run.get("id") or "") != run_id:
        raise WsError("run_not_found", "active run not found", status_code=404)
    handle = get_run_handle(run_id)
    if handle is None or handle.task.done():
        raise WsError("run_not_streaming", "run is not streaming in memory", status_code=404)
    if handle.session_id != session_id:
        raise WsError("run_mismatch", "run session mismatch", status_code=404)

    public_model = "locusagent-v1"
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    subscriber = attach_run_subscriber(handle)
    pending = drain_subscriber_queue_nowait(subscriber)
    run = await get_active_run(session_id)
    resume_sync = build_resume_sync_payload(run, pending)

    async def _stream():
        try:
            async for chunk in iter_run_sse(
                subscriber,
                chat_id=chat_id,
                public_model=public_model,
                created=created,
                session_id=session_id,
                run_id=run_id,
                resume_sync=resume_sync,
            ):
                yield chunk
        finally:
            detach_run_subscriber(handle, subscriber)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/cancel")
async def workspace_session_cancel_run(session_id: str) -> dict:
    lock = await session_lock(session_id)
    async with lock:
        cancelled = await cancel_active_run(session_id)
    return {"cancelled": cancelled}


@router.delete("/sessions/{session_id}")
async def workspace_delete_session(session_id: str) -> dict:
    lock = await session_lock(session_id)
    async with lock:
        await cancel_active_run(session_id)
        ok = await delete_session(session_id)
    if not ok:
        raise WsError("session_not_found", "session not found", status_code=404)
    return {"deleted": True}


class CategoryIn(BaseModel):
    name: str
    description: str = ""


class CategoryUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None


class ArtifactIn(BaseModel):
    title: str
    content: str
    type: Literal["markdown", "latex", "text"] = "markdown"
    category_id: str


class ArtifactUpdateIn(BaseModel):
    title: str | None = None
    content: str | None = None
    category_id: str | None = None


@router.get("/artifact-categories")
async def workspace_list_categories() -> dict:
    return {"items": await list_categories()}


@router.post("/artifact-categories", status_code=201)
async def workspace_create_category(payload: CategoryIn) -> dict:
    name = payload.name.strip()
    if not name:
        raise WsError("category_empty", "name is empty", status_code=400)
    return await create_category(name, payload.description.strip())


@router.put("/artifact-categories/{category_id}")
async def workspace_update_category(category_id: str, payload: CategoryUpdateIn) -> dict:
    if payload.name is None and payload.description is None:
        raise WsError("category_update_empty", "nothing to update", status_code=400)
    ok = await update_category(
        category_id,
        name=payload.name.strip() if payload.name is not None else None,
        description=payload.description.strip() if payload.description is not None else None,
    )
    if not ok:
        raise WsError("category_not_found", "category not found", status_code=404)
    return {"updated": True}


@router.delete("/artifact-categories/{category_id}")
async def workspace_delete_category(category_id: str) -> dict:
    ok = await delete_category(category_id)
    if not ok:
        raise WsError("category_not_found", "category not found", status_code=404)
    return {"deleted": True}


@router.get("/artifacts")
async def workspace_list_artifacts(category_id: str) -> dict:
    cid = category_id.strip()
    if not cid:
        raise WsError("category_required", "category_id is required", status_code=400)
    return {"items": await list_artifacts(cid)}


@router.get("/artifacts/{artifact_id}")
async def workspace_get_artifact(artifact_id: str) -> dict:
    item = await get_artifact(artifact_id)
    if item is None:
        raise WsError("artifact_not_found", "artifact not found", status_code=404)
    return item


@router.post("/artifacts", status_code=201)
async def workspace_create_artifact(payload: ArtifactIn) -> dict:
    title = payload.title.strip()
    if not title:
        raise WsError("artifact_empty", "title is empty", status_code=400)
    cid = payload.category_id.strip()
    if not cid:
        raise WsError("category_required", "category_id is required", status_code=400)
    try:
        return await create_artifact(
            title=title,
            content=payload.content,
            type=payload.type,
            category_id=cid,
        )
    except ValueError as exc:
        if str(exc) == "category not found":
            raise WsError("category_not_found", str(exc), status_code=404) from exc
        raise WsError("category_required", str(exc), status_code=400) from exc


@router.put("/artifacts/{artifact_id}")
async def workspace_update_artifact(artifact_id: str, payload: ArtifactUpdateIn) -> dict:
    if payload.title is None and payload.content is None and payload.category_id is None:
        raise WsError("artifact_update_empty", "nothing to update", status_code=400)
    cid: str | None = None
    if payload.category_id is not None:
        cid = payload.category_id.strip()
        if not cid:
            raise WsError("category_required", "category_id is required", status_code=400)
    try:
        ok = await update_artifact(
            artifact_id,
            title=payload.title.strip() if payload.title is not None else None,
            content=payload.content,
            category_id=cid,
        )
    except ValueError as exc:
        if str(exc) == "category not found":
            raise WsError("category_not_found", str(exc), status_code=404) from exc
        raise WsError("category_required", str(exc), status_code=400) from exc
    if not ok:
        raise WsError("artifact_not_found", "artifact not found", status_code=404)
    return {"updated": True}


@router.delete("/artifacts/{artifact_id}")
async def workspace_delete_artifact(artifact_id: str) -> dict:
    ok = await delete_artifact(artifact_id)
    if not ok:
        raise WsError("artifact_not_found", "artifact not found", status_code=404)
    return {"deleted": True}
