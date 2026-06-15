"""mcp_view / mcp_manage / mcp_refresh：MCP 服务查询、增删改与重连。"""

from __future__ import annotations

from typing import Any

from ..db import run_in_thread
from ..mcp_.config import (
    MCPServerConfig,
    add_mcp_server,
    get_mcp_server,
    list_mcp_servers,
    remove_mcp_server,
    update_mcp_server,
)
from ..mcp_.probe import McpProbeError, build_http_mcp_config
from ..tool_settings import is_mcp_server_enabled
from .args import pick_action, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


def _mcp_runtime() -> dict[str, dict[str, Any]]:
    from ..mcp_.client import list_mcp_runtime
    return list_mcp_runtime()


async def _mcp_view(_args: dict[str, Any]) -> ToolResult:
    servers = [s for s in await run_in_thread(list_mcp_servers) if is_mcp_server_enabled(s.name)]
    if not servers:
        return ToolResult(content="(no mcp servers)", metadata={"servers": []})
    runtime = _mcp_runtime()
    lines: list[str] = []
    out: list[dict[str, Any]] = []
    for s in servers:
        r = runtime.get(s.name, {})
        connected = bool(r.get("connected", False))
        tools = list(r.get("tools", []))
        tool_names = ", ".join(t.get("name", "") for t in tools[:8] if t.get("name"))
        tool_suffix = f" | tools={len(tools)}" + (f": {tool_names}" if tool_names else "")
        if s.transport == "stdio":
            lines.append(
                f"- {s.name} [stdio] {' '.join(s.command + s.args)}"
                f" | connected={connected}{tool_suffix}"
            )
        else:
            lines.append(
                f"- {s.name} [http] {s.url}"
                f" | connected={connected}{tool_suffix}"
            )
        d = s.to_public_dict()
        d["connected"] = connected
        d["tools"] = tools
        d["tool_count"] = len(tools)
        out.append(d)
    return ToolResult(content="\n".join(lines), metadata={"servers": out})


async def _add_mcp(args: dict[str, Any]) -> ToolResult:
    name = pick_str(args, "name")
    if not name:
        raise ToolError("name is required")
    transport = str(args.get("transport", "stdio")).strip().lower()
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

    from ..mcp_.client import connect_mcp_server
    from ..workspace import get_workspace_id
    from ..workspace_runtime import invalidate_mcp_runtime, mark_mcp_runtime_ready

    wid = get_workspace_id()
    invalidate_mcp_runtime(wid)
    runtime = await connect_mcp_server(cfg)
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


async def _update_mcp(args: dict[str, Any]) -> ToolResult:
    name = pick_str(args, "name")
    if not name:
        raise ToolError("name is required")
    existing = await run_in_thread(get_mcp_server, name)
    if existing is None:
        raise ToolError(f"mcp server not found: {name}")

    new_name = pick_str(args, "new_name") or name
    transport = str(args.get("transport", existing.transport)).strip().lower()
    if transport not in {"stdio", "http"}:
        raise ToolError("transport must be stdio or http")

    if transport == "stdio":
        cmd = list(args["command"] if "command" in args else existing.command)
        mcp_args = list(args["args"] if "args" in args else existing.args)
        env_map = dict(args["env"] if "env" in args else existing.env)
        cfg = MCPServerConfig(
            name=new_name, transport="stdio", command=cmd, args=mcp_args, env=env_map, auth="none"
        )
    else:
        url = str(args["url"]).strip() if "url" in args else (existing.url or "").strip()
        if not url:
            raise ToolError("url is required for http transport")
        header_map = dict(args["headers"] if "headers" in args else existing.headers)
        try:
            cfg = await build_http_mcp_config(
                name=new_name,
                url=url,
                headers=header_map,
                existing=existing if (existing.url or "").strip() == url else None,
            )
        except McpProbeError as exc:
            raise ToolError(str(exc)) from exc

    try:
        updated = await run_in_thread(update_mcp_server, name, cfg)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except (ValueError, FileExistsError) as exc:
        raise ToolError(str(exc)) from exc

    from ..workspace import get_workspace_id, mcp_tool_category
    from ..workspace_runtime import mark_mcp_runtime_ready, refresh_mcp_server
    from .registry import registry

    wid = get_workspace_id()
    runtime = await refresh_mcp_server(wid, updated.name)
    mark_mcp_runtime_ready(wid)
    enabled = is_mcp_server_enabled(updated.name)
    target = mcp_tool_category(updated.name, wid)
    for tool in registry.all():
        if tool.category == target:
            tool.enabled = enabled
    if runtime.get("connected"):
        return ToolResult(
            content=f"mcp server '{updated.name}' updated and connected, tools={len(runtime.get('tools', []))}",
            metadata=runtime,
        )
    return ToolResult(
        content=f"mcp server '{updated.name}' updated but connect failed: {runtime.get('error', 'unknown')}",
        metadata=runtime,
    )


async def _refresh_mcp(args: dict[str, Any]) -> ToolResult:
    name = pick_str(args, "name")
    if not name:
        raise ToolError("name is required")
    existing = await run_in_thread(get_mcp_server, name)
    if existing is None:
        raise ToolError(f"mcp server not found: {name}")

    from ..workspace import get_workspace_id, mcp_tool_category
    from ..workspace_runtime import mark_mcp_runtime_ready, refresh_mcp_server
    from .registry import registry

    wid = get_workspace_id()
    runtime = await refresh_mcp_server(wid, name)
    mark_mcp_runtime_ready(wid)
    enabled = is_mcp_server_enabled(name)
    target = mcp_tool_category(name, wid)
    for tool in registry.all():
        if tool.category == target:
            tool.enabled = enabled
    if runtime.get("connected"):
        return ToolResult(
            content=f"mcp server '{name}' refreshed and connected, tools={len(runtime.get('tools', []))}",
            metadata=runtime,
        )
    return ToolResult(
        content=f"mcp server '{name}' refresh failed: {runtime.get('error', 'unknown')}",
        metadata=runtime,
    )


async def _remove_mcp(args: dict[str, Any]) -> ToolResult:
    name = pick_str(args, "name")
    if not name:
        raise ToolError("name is required")
    ok = await run_in_thread(remove_mcp_server, name)
    if not ok:
        raise ToolError(f"mcp server not found: {name}")
    from ..workspace import get_workspace_id
    from ..workspace_runtime import disconnect_mcp_server_runtime

    await disconnect_mcp_server_runtime(get_workspace_id(), name)
    return ToolResult(content=f"mcp server '{name}' removed")


async def _mcp_manage(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)
    if action in {"edit", "update"}:
        return await _update_mcp(args)
    if action in {"remove", "delete"}:
        return await _remove_mcp(args)
    if action == "add":
        return await _add_mcp(args)
    raise ToolError(f"unknown action: {action}; use add / update / remove")


register_builtin(
    Tool(
        name="mcp_view",
        description="列出当前工作区全部 MCP 服务、连接状态与暴露的工具数量。",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_mcp_view,
    )
)


register_builtin(
    Tool(
        name="mcp_refresh",
        description=(
            "重连指定 MCP 服务并同步工具列表（OAuth 完成后、连接异常或工具变更后使用）。"
            "查询状态用 mcp_view；增删改配置用 mcp_manage。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "MCP 服务名（必填）。"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_refresh_mcp,
    )
)


register_builtin(
    Tool(
        name="mcp_manage",
        description=(
            "管理 MCP 服务连接：add（新增）/ update（更新配置）/ remove（移除）。\n"
            "查询用 mcp_view；重连/刷新工具列表用 mcp_refresh；不能创建/删除/切换 AgentPod 工作区。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "update", "remove", "edit", "delete"],
                    "description": "操作类型。",
                },
                "name": {"type": "string", "description": "MCP 服务名（必填）。"},
                "new_name": {"type": "string", "description": "update 时重命名（可选）。"},
                "transport": {
                    "type": "string",
                    "enum": ["stdio", "http"],
                    "description": "传输方式，默认继承已有配置。",
                },
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "stdio 启动命令（例如 ['npx', '-y', '@scope/server']）。",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "stdio 附加参数。",
                },
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "stdio 环境变量。",
                },
                "url": {"type": "string", "description": "http 服务地址。"},
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "http 请求头（如 Authorization: Bearer xxx）。",
                },
            },
            "required": ["action", "name"],
        },
        handler=_mcp_manage,
    )
)
