"""MCP 客户端：启动时建立 session，发现 tools 注册到 ToolRegistry。

支持：
- stdio：fork 子进程（继承容器约束 user/cap/seccomp）
- streamable HTTP：URL 必须在出网白名单内（由网络层强制，本模块不再二次校验）

约束：
- 单个 server 失败不影响其他流程（捕获异常仅记日志）。
- 名字冲突：MCP 工具以 `mcp__{server}__{tool}` 命名，避免与内置工具碰撞。
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..config import get_settings
from ..logging import get_logger
from ..tool_settings import is_mcp_server_enabled
from ..tools import Tool, ToolError, ToolResult
from ..tools import registry as tool_registry
from ..workspace import workspace_data_dir
from .config import MCPServerConfig, get_mcp_server, list_mcp_servers

log = get_logger("mcp")


def _stdio_env(cfg: MCPServerConfig) -> dict[str, str]:
    """只读根文件系统 + /tmp noexec：npx 缓存必须落在可执行的 /data volume。"""
    data_dir = workspace_data_dir()
    base = {
        "HOME": str(data_dir),
        "NPM_CONFIG_CACHE": str(data_dir / ".npm-cache"),
        "XDG_CACHE_HOME": str(data_dir / ".cache"),
    }
    base.update(cfg.env or {})
    return base


class MCPManager:
    def __init__(self) -> None:
        self._started = False
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._registered_tool_names: dict[str, list[str]] = {}
        self._tool_catalog: dict[str, list[dict[str, Any]]] = {}
        self._reconnect_locks: dict[str, asyncio.Lock] = {}
        self._last_errors: dict[str, str] = {}

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        servers = list_mcp_servers()
        for cfg in servers:
            try:
                await self._connect(cfg)
            except Exception as exc:
                log.error("mcp_connect_failed", server=cfg.name, error=str(exc))

    async def _connect(self, cfg: MCPServerConfig) -> None:
        if cfg.name in self._sessions:
            return
        stack = AsyncExitStack()
        if cfg.transport == "stdio":
            params = StdioServerParameters(
                command=cfg.command[0] if cfg.command else "",
                args=cfg.command[1:] + cfg.args if len(cfg.command) > 1 else cfg.args,
                env=_stdio_env(cfg),
            )
            read, write = await stack.enter_async_context(stdio_client(params))
        elif cfg.transport == "http":
            if not cfg.url:
                raise ValueError("http transport requires url")
            transport = await stack.enter_async_context(streamablehttp_client(cfg.url))
            read, write, _ = transport
        else:
            raise ValueError(f"unknown transport: {cfg.transport}")

        try:
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[cfg.name] = session
            self._stacks[cfg.name] = stack
            await self._register_tools(cfg.name, session)
            log.info("mcp_connected", server=cfg.name, transport=cfg.transport)
        except Exception:
            await stack.aclose()
            raise

    async def _register_tools(self, server_name: str, session: ClientSession) -> None:
        listed = await session.list_tools()
        names: list[str] = []
        catalog: list[dict[str, Any]] = []
        for tool_def in listed.tools:
            full_name = f"mcp__{server_name}__{tool_def.name}"
            description = tool_def.description or f"MCP tool {tool_def.name}@{server_name}"
            schema = tool_def.inputSchema or {"type": "object", "properties": {}}
            schema_summary = _schema_summary(schema)

            async def _handler(args: dict[str, Any], _server=server_name, _name=tool_def.name) -> ToolResult:
                try:
                    result = await self._call_tool_with_retry(_server, _name, args)
                except Exception as exc:
                    raise ToolError(f"mcp call failed: {exc}") from exc
                if getattr(result, "isError", False):
                    raise ToolError(_extract_text(result))
                return ToolResult(content=_extract_text(result))

            tool_registry.register(
                Tool(
                    name=full_name,
                    description=description,
                    parameters=schema,
                    handler=_handler,
                    enabled=is_mcp_server_enabled(server_name),
                    category=f"mcp:{server_name}",
                )
            )
            names.append(full_name)
            catalog.append(
                {
                    "name": tool_def.name,
                    "full_name": full_name,
                    "description": description,
                    "input_schema": schema,
                    "schema_summary": schema_summary,
                }
            )
        self._registered_tool_names[server_name] = names
        self._tool_catalog[server_name] = catalog
        log.info("mcp_tools_registered", server=server_name, count=len(listed.tools))

    async def _call_tool_with_retry(
        self,
        server_name: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> Any:
        timeout_seconds = max(1.0, float(get_settings().mcp_call_timeout_seconds))
        request_id = uuid4().hex[:12]

        async def _call_with_timeout(sess: ClientSession, *, phase: str) -> Any:
            started = time.monotonic()
            log.info(
                "mcp_call_started",
                request_id=request_id,
                server=server_name,
                tool=tool_name,
                phase=phase,
                timeout_seconds=timeout_seconds,
            )
            try:
                result = await asyncio.wait_for(sess.call_tool(tool_name, args), timeout=timeout_seconds)
            except TimeoutError:
                elapsed = round(time.monotonic() - started, 3)
                log.warning(
                    "mcp_call_timeout",
                    request_id=request_id,
                    server=server_name,
                    tool=tool_name,
                    phase=phase,
                    elapsed_seconds=elapsed,
                    timeout_seconds=timeout_seconds,
                )
                raise
            except Exception as exc:
                elapsed = round(time.monotonic() - started, 3)
                log.warning(
                    "mcp_call_failed",
                    request_id=request_id,
                    server=server_name,
                    tool=tool_name,
                    phase=phase,
                    elapsed_seconds=elapsed,
                    error=str(exc),
                )
                raise
            elapsed = round(time.monotonic() - started, 3)
            log.info(
                "mcp_call_succeeded",
                request_id=request_id,
                server=server_name,
                tool=tool_name,
                phase=phase,
                elapsed_seconds=elapsed,
            )
            return result

        session = self._sessions.get(server_name)
        if session is None:
            raise RuntimeError(f"mcp server not connected: {server_name}")
        try:
            return await _call_with_timeout(session, phase="initial")
        except Exception as first_exc:
            log.warning(
                "mcp_call_failed_retrying",
                request_id=request_id,
                server=server_name,
                tool=tool_name,
                error=str(first_exc),
            )
            await self.reconnect_server(server_name)
            session2 = self._sessions.get(server_name)
            if session2 is None:
                raise first_exc
            try:
                return await _call_with_timeout(session2, phase="retry")
            except TimeoutError as retry_timeout:
                raise TimeoutError(
                    f"mcp tool call timeout after {timeout_seconds:.1f}s "
                    f"(server={server_name}, tool={tool_name})"
                ) from retry_timeout

    async def add_server(self, cfg: MCPServerConfig) -> dict[str, Any]:
        try:
            await self._connect(cfg)
        except Exception as exc:
            log.error("mcp_runtime_add_failed", server=cfg.name, error=str(exc))
            self._last_errors[cfg.name] = str(exc)
            return {
                "name": cfg.name,
                "connected": False,
                "tools": [],
                "error": str(exc),
            }
        self._last_errors.pop(cfg.name, None)
        return {
            "name": cfg.name,
            "connected": True,
            "tools": self._tool_catalog.get(cfg.name, []),
            "error": None,
        }

    async def reconnect_server(self, server_name: str) -> dict[str, Any]:
        cfg = get_mcp_server(server_name)
        if cfg is None:
            return {"name": server_name, "connected": False, "tools": [], "error": "server not found"}
        lock = self._reconnect_locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            await self.remove_server(server_name)
            return await self.add_server(cfg)

    async def probe_server(self, cfg: MCPServerConfig) -> dict[str, Any]:
        stack = AsyncExitStack()
        try:
            if cfg.transport == "stdio":
                params = StdioServerParameters(
                    command=cfg.command[0] if cfg.command else "",
                    args=cfg.command[1:] + cfg.args if len(cfg.command) > 1 else cfg.args,
                    env=_stdio_env(cfg),
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif cfg.transport == "http":
                if not cfg.url:
                    raise ValueError("http transport requires url")
                transport = await stack.enter_async_context(streamablehttp_client(cfg.url))
                read, write, _ = transport
            else:
                raise ValueError(f"unknown transport: {cfg.transport}")
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "full_name": f"mcp__{cfg.name}__{t.name}",
                    "description": t.description or f"MCP tool {t.name}@{cfg.name}",
                    "input_schema": t.inputSchema or {"type": "object", "properties": {}},
                    "schema_summary": _schema_summary(t.inputSchema or {"type": "object", "properties": {}}),
                }
                for t in listed.tools
            ]
            return {"name": cfg.name, "connected": True, "tools": tools, "error": None}
        except Exception as exc:
            return {"name": cfg.name, "connected": False, "tools": [], "error": str(exc)}
        finally:
            await stack.aclose()

    async def remove_server(self, server_name: str) -> bool:
        tool_names = self._registered_tool_names.pop(server_name, [])
        for name in tool_names:
            tool_registry.unregister(name)
        self._tool_catalog.pop(server_name, None)
        self._sessions.pop(server_name, None)
        stack = self._stacks.pop(server_name, None)
        if stack is not None:
            try:
                await stack.aclose()
            except Exception as exc:
                log.warning("mcp_server_close_error", server=server_name, error=str(exc))
        return bool(tool_names or stack is not None)

    def runtime_servers(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        all_servers = set(self._sessions.keys()) | set(self._tool_catalog.keys())
        for name in all_servers:
            out[name] = {
                "connected": name in self._sessions,
                "tools": list(self._tool_catalog.get(name, [])),
                "error": self._last_errors.get(name),
            }
        return out

    async def stop(self) -> None:
        for server_name in list(self._sessions.keys() | self._stacks.keys() | self._registered_tool_names.keys()):
            await self.remove_server(server_name)
        self._registered_tool_names.clear()
        self._tool_catalog.clear()
        self._sessions.clear()
        self._stacks.clear()
        self._reconnect_locks.clear()
        self._last_errors.clear()
        self._started = False


def _extract_text(result: Any) -> str:
    parts = []
    for c in getattr(result, "content", None) or []:
        text = getattr(c, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts) if parts else str(result)


def _schema_summary(schema: dict[str, Any]) -> list[dict[str, Any]]:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    out: list[dict[str, Any]] = []
    for name, info in props.items():
        if not isinstance(info, dict):
            continue
        out.append(
            {
                "name": name,
                "type": info.get("type", "any"),
                "required": name in required,
                "enum": info.get("enum") if isinstance(info.get("enum"), list) else None,
            }
        )
    return out


_manager = MCPManager()


async def start_mcp() -> None:
    await _manager.start()


async def stop_mcp() -> None:
    await _manager.stop()


async def connect_mcp_server(cfg: MCPServerConfig) -> dict[str, Any]:
    return await _manager.add_server(cfg)


async def disconnect_mcp_server(server_name: str) -> bool:
    return await _manager.remove_server(server_name)


def list_mcp_runtime() -> dict[str, dict[str, Any]]:
    return _manager.runtime_servers()


async def reconnect_mcp_server(server_name: str) -> dict[str, Any]:
    return await _manager.reconnect_server(server_name)


async def probe_mcp_server(cfg: MCPServerConfig) -> dict[str, Any]:
    return await _manager.probe_server(cfg)


async def reconnect_all_mcp_servers() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for cfg in list_mcp_servers():
        results[cfg.name] = await _manager.reconnect_server(cfg.name)
    return results
