"""manage_workspace：高层工作区操作，目前覆盖 MCP 配置 CRUD + 状态摘要。

具体 Skills/Memory CRUD 仍走 skill_manage / memory，便于审计与权限拆分。
"""

from __future__ import annotations

from typing import Any

from ..db import run_in_thread
from ..mcp_.probe import McpProbeError, build_http_mcp_config
from ..memory import count_memories
from ..skills import list_skills
from ..tool_settings import is_mcp_server_enabled, is_skill_enabled
from .base import Tool, ToolError, ToolResult, register_builtin


def _list_mcp_runtime():
    from ..mcp_.client import list_mcp_runtime

    return list_mcp_runtime()


async def _summary() -> ToolResult:
    skills = [s for s in await run_in_thread(list_skills) if is_skill_enabled(s.name)]
    servers = [s for s in await run_in_thread(list_mcp_servers) if is_mcp_server_enabled(s.name)]
    mem_count = await count_memories()
    lines = [
        f"skills: {len(skills)} ({sum(1 for s in skills if s.source == 'public')} public + {sum(1 for s in skills if s.source == 'private')} private)",
        f"mcp_servers: {len(servers)}",
        f"memory_entries: {mem_count}",
    ]
    return ToolResult(content="\n".join(lines))


async def _list_mcp() -> ToolResult:
    servers = [s for s in await run_in_thread(list_mcp_servers) if is_mcp_server_enabled(s.name)]
    if not servers:
        return ToolResult(content="(no mcp servers)")
    runtime = _list_mcp_runtime()
    lines = []
    out_servers: list[dict[str, Any]] = []
    for s in servers:
        r = runtime.get(s.name, {})
        tools = list(r.get("tools", []))
        tool_names = ", ".join(t.get("name", "") for t in tools[:8] if t.get("name"))
        tool_suffix = f" | tools={len(tools)}" + (f": {tool_names}" if tool_names else "")
        if s.transport == "stdio":
            lines.append(
                f"- {s.name} [stdio] {' '.join(s.command + s.args)}"
                f" | connected={bool(r.get('connected', False))}{tool_suffix}"
            )
        else:
            lines.append(
                f"- {s.name} [http] {s.url}"
                f" | connected={bool(r.get('connected', False))}{tool_suffix}"
            )
        d = s.to_public_dict()
        d["connected"] = bool(r.get("connected", False))
        d["tools"] = tools
        d["tool_count"] = len(tools)
        out_servers.append(d)
    return ToolResult(content="\n".join(lines), metadata={"servers": out_servers})


async def _add_mcp(args: dict[str, Any]) -> ToolResult:
    transport = str(args.get("transport", "stdio")).strip()
    name = str(args.get("name", "")).strip()
    if transport == "stdio":
        cfg = MCPServerConfig(
            name=name,
            transport="stdio",
            command=list(args.get("command", []) or []),
            args=list(args.get("args", []) or []),
            env=dict(args.get("env", {}) or {}),
            auth="none",
        )
    else:
        url = str(args.get("url", "")).strip()
        if not url:
            raise ToolError("url is required for http transport")
        try:
            cfg = await build_http_mcp_config(
                name=name,
                url=url,
                headers=dict(args.get("headers", {}) or {}),
            )
        except McpProbeError as exc:
            raise ToolError(str(exc)) from exc
    try:
        await run_in_thread(add_mcp_server, cfg)
    except (ValueError, FileExistsError) as exc:
        raise ToolError(str(exc)) from exc
    from ..mcp_.client import connect_mcp_server, ensure_mcp_started, sync_mcp_tools_for_workspace
    from ..workspace import get_workspace_id
    from ..workspace_runtime import invalidate_mcp_runtime, mark_mcp_runtime_ready

    wid = get_workspace_id()
    invalidate_mcp_runtime(wid)
    await ensure_mcp_started(wid)
    runtime = await connect_mcp_server(cfg)
    await sync_mcp_tools_for_workspace(wid)
    mark_mcp_runtime_ready(wid)
    if runtime.get("connected"):
        return ToolResult(
            content=f"mcp server '{cfg.name}' added and connected, tools={len(runtime.get('tools', []))}",
            metadata=runtime,
        )
    return ToolResult(
        content=f"mcp server '{cfg.name}' added but connect failed: {runtime.get('error', 'unknown')}",
        metadata=runtime,
    )


async def _remove_mcp(args: dict[str, Any]) -> ToolResult:
    name = str(args.get("name", "")).strip()
    if not name:
        raise ToolError("name is required")
    ok = await run_in_thread(remove_mcp_server, name)
    if not ok:
        raise ToolError(f"mcp server not found: {name}")
    from ..workspace import get_workspace_id
    from ..workspace_runtime import disconnect_mcp_server_runtime

    await disconnect_mcp_server_runtime(get_workspace_id(), name)
    return ToolResult(content=f"mcp server '{name}' removed")


async def _manage_workspace(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action", "summary")).lower()
    if action == "summary":
        return await _summary()
    if action == "list_mcp":
        return await _list_mcp()
    if action == "add_mcp":
        return await _add_mcp(args)
    if action == "remove_mcp":
        return await _remove_mcp(args)
    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="manage_workspace",
        description=(
            "工作区运维级管理工具：查看摘要、管理 MCP 服务连接。"
            "用于“环境状态盘点”“MCP 服务增删与排障”这类基础设施任务，"
            "而不是常规业务内容生成。"
            "支持动作：summary / list_mcp / add_mcp / remove_mcp。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["summary", "list_mcp", "add_mcp", "remove_mcp"],
                    "description": "执行动作：摘要、列出 MCP、新增 MCP、移除 MCP。",
                },
                "name": {"type": "string", "description": "MCP 服务名（add_mcp/remove_mcp 必填）。"},
                "transport": {
                    "type": "string",
                    "enum": ["stdio", "http"],
                    "description": "MCP 传输方式（add_mcp 时使用）。",
                },
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "stdio 模式启动命令（例如 ['npx','-y','@xxx/server']）。",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "stdio 模式附加参数。",
                },
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "stdio 模式环境变量。",
                },
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "http 模式请求头（如 Authorization: Bearer xxx）。",
                },
                "url": {"type": "string", "description": "http 模式服务地址。"},
            },
            "required": ["action"],
        },
        handler=_manage_workspace,
    )
)
