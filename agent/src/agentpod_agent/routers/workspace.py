"""容器内 /workspace/* 路由：Skills / MCP / Memory / Sessions CRUD。

宿主**不直接写**用户 volume，所有写入由此处统一。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import verify_internal_token
from ..core import (
    cancel_active_run,
    delete_session,
    get_active_run,
    list_messages,
    list_sessions,
    session_lock,
)
from ..db import run_in_thread
from ..errors import WsError
from ..mcp_ import (
    MCPServerConfig,
    add_mcp_server,
    get_mcp_server,
    list_mcp_servers,
    remove_mcp_server,
    update_mcp_server,
)
from ..mcp_.client import (
    connect_mcp_server,
    disconnect_mcp_server,
    list_mcp_runtime,
    probe_mcp_server,
    reconnect_mcp_server,
)
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
    list_skills,
    update_skill,
)
from ..tool_settings import (
    is_mcp_server_enabled,
    is_skill_enabled,
    set_builtin_tool_enabled,
    set_mcp_server_enabled,
    set_skill_enabled,
)
from ..tools import registry as tool_registry

router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
    dependencies=[Depends(verify_internal_token)],
)


class SkillIn(BaseModel):
    name: str
    description: str = ""
    body: str = ""
    triggers: list[str] = Field(default_factory=list)


class SkillUpdateIn(BaseModel):
    description: str | None = None
    body: str | None = None
    triggers: list[str] | None = None


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


@router.post("/skills", status_code=201)
async def workspace_create_skill(payload: SkillIn) -> dict:
    skill = Skill(
        name=payload.name,
        description=payload.description,
        body=payload.body,
        triggers=payload.triggers,
        source="private",
    )
    try:
        created = await run_in_thread(create_skill, skill)
    except FileExistsError as exc:
        raise WsError("skill_exists", str(exc), status_code=409) from exc
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
            triggers=payload.triggers,
        )
    except ValueError as exc:
        raise WsError("skill_invalid", str(exc), status_code=400) from exc
    except FileNotFoundError as exc:
        raise WsError("skill_not_found", str(exc), status_code=404) from exc
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
    return {"deleted": True}


class MCPIn(BaseModel):
    name: str
    transport: Literal["stdio", "http"]
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None


class ToolToggleIn(BaseModel):
    enabled: bool


@router.get("/tools")
async def workspace_list_tools() -> dict:
    skills = await run_in_thread(list_skills)
    mcp_servers = await run_in_thread(list_mcp_servers)
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
    return {
        "builtin_tools": builtins,
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "source": s.source,
                "enabled": is_skill_enabled(s.name),
            }
            for s in skills
        ],
        "mcp_servers": [
            {
                "name": s.name,
                "transport": s.transport,
                "enabled": is_mcp_server_enabled(s.name),
            }
            for s in mcp_servers
        ],
    }


@router.put("/tools/builtin/{name}")
async def workspace_toggle_builtin_tool(name: str, payload: ToolToggleIn) -> dict:
    tool = tool_registry.get(name)
    if tool is None or tool.category != "builtin":
        raise WsError("tool_not_found", "builtin tool not found", status_code=404)
    tool.enabled = payload.enabled
    await run_in_thread(set_builtin_tool_enabled, name, payload.enabled)
    return {"name": name, "enabled": payload.enabled}


@router.put("/tools/skills/{name}")
async def workspace_toggle_skill(name: str, payload: ToolToggleIn) -> dict:
    skill = await run_in_thread(get_skill, name)
    if skill is None:
        raise WsError("skill_not_found", "skill not found", status_code=404)
    await run_in_thread(set_skill_enabled, name, payload.enabled)
    return {"name": name, "enabled": payload.enabled}


@router.put("/tools/mcp/{name}")
async def workspace_toggle_mcp(name: str, payload: ToolToggleIn) -> dict:
    cfg = await run_in_thread(get_mcp_server, name)
    if cfg is None:
        raise WsError("mcp_not_found", "mcp server not found", status_code=404)
    await run_in_thread(set_mcp_server_enabled, name, payload.enabled)
    _set_mcp_tools_enabled(name, payload.enabled)
    return {"name": name, "enabled": payload.enabled}


def _mcp_item_with_runtime(cfg: MCPServerConfig, runtime: dict[str, dict]) -> dict:
    d = cfg.to_dict()
    r = runtime.get(cfg.name, {})
    d["enabled"] = is_mcp_server_enabled(cfg.name)
    d["connected"] = bool(r.get("connected", False))
    d["tools"] = r.get("tools", [])
    d["tool_count"] = len(d["tools"])
    if r.get("error"):
        d["runtime_error"] = r["error"]
    return d


def _mcp_response(cfg: MCPServerConfig, runtime: dict[str, object]) -> dict:
    d = cfg.to_dict()
    d["enabled"] = is_mcp_server_enabled(cfg.name)
    d["connected"] = bool(runtime.get("connected", False))
    d["tools"] = runtime.get("tools", [])
    d["tool_count"] = len(d["tools"])
    if runtime.get("error"):
        d["runtime_error"] = runtime["error"]
    return d


def _set_mcp_tools_enabled(server_name: str, enabled: bool) -> None:
    target = f"mcp:{server_name}"
    for tool in tool_registry.all():
        if tool.category == target:
            tool.enabled = enabled


def _to_mcp_cfg(payload: MCPIn) -> MCPServerConfig:
    return MCPServerConfig(
        name=payload.name.strip(),
        transport=payload.transport,
        command=payload.command,
        args=payload.args,
        env=payload.env,
        url=payload.url,
    )


@router.get("/mcp")
async def workspace_list_mcp() -> dict:
    servers = await run_in_thread(list_mcp_servers)
    runtime = list_mcp_runtime()
    return {"items": [_mcp_item_with_runtime(s, runtime) for s in servers]}


@router.post("/mcp", status_code=201)
async def workspace_add_mcp(payload: MCPIn) -> dict:
    cfg = _to_mcp_cfg(payload)
    try:
        added = await run_in_thread(add_mcp_server, cfg)
    except (ValueError, FileExistsError) as exc:
        raise WsError("mcp_invalid", str(exc), status_code=400) from exc
    runtime = await connect_mcp_server(added)
    return _mcp_response(added, runtime)


@router.post("/mcp/test")
async def workspace_test_mcp(payload: MCPIn) -> dict:
    cfg = _to_mcp_cfg(payload)
    tested = await probe_mcp_server(cfg)
    return _mcp_response(cfg, tested)


@router.put("/mcp/{name}")
async def workspace_update_mcp(name: str, payload: MCPIn) -> dict:
    cfg = _to_mcp_cfg(payload)
    try:
        updated = await run_in_thread(update_mcp_server, name, cfg)
    except FileNotFoundError as exc:
        raise WsError("mcp_not_found", str(exc), status_code=404) from exc
    except (ValueError, FileExistsError) as exc:
        raise WsError("mcp_invalid", str(exc), status_code=400) from exc
    runtime = await reconnect_mcp_server(updated.name)
    enabled = is_mcp_server_enabled(updated.name)
    _set_mcp_tools_enabled(updated.name, enabled)
    d = updated.to_dict()
    d["enabled"] = enabled
    d["connected"] = bool(runtime.get("connected", False))
    d["tools"] = runtime.get("tools", [])
    d["tool_count"] = len(d["tools"])
    if runtime.get("error"):
        d["runtime_error"] = runtime["error"]
    return d


@router.post("/mcp/{name}")
async def workspace_reconnect_mcp(name: str) -> dict:
    cfg = await run_in_thread(get_mcp_server, name)
    if cfg is None:
        raise WsError("mcp_not_found", "mcp server not found", status_code=404)
    runtime = await reconnect_mcp_server(name)
    enabled = is_mcp_server_enabled(name)
    _set_mcp_tools_enabled(name, enabled)
    d = cfg.to_dict()
    d["enabled"] = enabled
    d["connected"] = bool(runtime.get("connected", False))
    d["tools"] = runtime.get("tools", [])
    d["tool_count"] = len(d["tools"])
    if runtime.get("error"):
        d["runtime_error"] = runtime["error"]
    return d


@router.delete("/mcp/{name}")
async def workspace_remove_mcp(name: str) -> dict:
    ok = await run_in_thread(remove_mcp_server, name)
    if not ok:
        raise WsError("mcp_not_found", "mcp server not found", status_code=404)
    await disconnect_mcp_server(name)
    return {"deleted": True}


class MemoryIn(BaseModel):
    content: str
    anchor: Literal["identity", "experience"] = "experience"


class MemoryUpdateIn(BaseModel):
    content: str | None = None
    anchor: Literal["identity", "experience"] | None = None


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
    return {"id": mid}


@router.put("/memory/{entry_id}")
async def workspace_update_memory(entry_id: int, payload: MemoryUpdateIn) -> dict:
    if payload.content is None and payload.anchor is None:
        raise WsError("memory_update_empty", "nothing to update", status_code=400)
    ok = await update_memory(entry_id, payload.content, anchor=payload.anchor)
    if not ok:
        raise WsError("memory_not_found", "memory not found", status_code=404)
    if payload.content is not None:
        await enqueue_embedding(entry_id)
    return {"updated": True}


@router.delete("/memory/{entry_id}")
async def workspace_delete_memory(entry_id: int) -> dict:
    ok = await delete_memory(entry_id)
    if not ok:
        raise WsError("memory_not_found", "memory not found", status_code=404)
    return {"deleted": True}


@router.get("/sessions")
async def workspace_list_sessions(limit: int = 50) -> dict:
    items = await list_sessions(limit=limit)
    return {"items": items}


@router.get("/sessions/{session_id}")
async def workspace_session_messages(session_id: str) -> dict:
    items = await list_messages(session_id)
    return {"items": items}


@router.get("/sessions/{session_id}/active-run")
async def workspace_session_active_run(session_id: str) -> dict:
    run = await get_active_run(session_id)
    return {"run": run}


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
