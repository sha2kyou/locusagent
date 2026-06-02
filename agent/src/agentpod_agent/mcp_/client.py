"""MCP 客户端：按工作区隔离 manager，工具注册带 workspace 前缀 category。"""

from __future__ import annotations

import asyncio
import time
from contextlib import AsyncExitStack
from typing import Any
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..config import get_settings
from ..logging import get_logger
from ..tool_settings import is_mcp_server_enabled
from ..tools import Tool, ToolError, ToolResult
from ..tools import registry as tool_registry
from ..workspace import (
    get_workspace_id,
    mcp_tool_category,
    mcp_tool_full_name,
    normalize_workspace_id,
    workspace_data_dir,
)
from .config import MCPServerConfig, get_mcp_server, list_mcp_servers
from .oauth import OAuthRequiredError, connect_http_oauth_session, probe_http_oauth

log = get_logger("mcp")

_managers_lock = asyncio.Lock()


def _stdio_env(cfg: MCPServerConfig, workspace_id: str) -> dict[str, str]:
    data_dir = workspace_data_dir(workspace_id)
    base = {
        "HOME": str(data_dir),
        "NPM_CONFIG_CACHE": str(data_dir / ".npm-cache"),
        "XDG_CACHE_HOME": str(data_dir / ".cache"),
    }
    base.update(cfg.env or {})
    return base


class MCPManager:
    def __init__(self, workspace_id: str) -> None:
        self._workspace_id = normalize_workspace_id(workspace_id)
        self._started = False
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._registered_tool_names: dict[str, list[str]] = {}
        self._tool_catalog: dict[str, list[dict[str, Any]]] = {}
        self._reconnect_locks: dict[str, asyncio.Lock] = {}
        self._tools_lock = asyncio.Lock()
        self._last_errors: dict[str, str] = {}

    async def _discard_connect_state(self, server_name: str, stack: AsyncExitStack) -> None:
        self._sessions.pop(server_name, None)
        self._stacks.pop(server_name, None)
        self._registered_tool_names.pop(server_name, None)
        self._tool_catalog.pop(server_name, None)
        try:
            await stack.aclose()
        except Exception as exc:
            log.warning(
                "mcp_connect_discard_close_error",
                server=server_name,
                workspace_id=self._workspace_id,
                error=str(exc),
            )

    async def _connect_timed(self, cfg: MCPServerConfig) -> None:
        timeout = max(1.0, float(get_settings().mcp_connect_timeout_seconds))
        try:
            await asyncio.wait_for(self._connect(cfg), timeout=timeout)
        except TimeoutError:
            await self.remove_server(cfg.name)
            msg = f"connect timeout after {timeout}s"
            self._last_errors[cfg.name] = msg
            log.error(
                "mcp_connect_timeout",
                server=cfg.name,
                workspace_id=self._workspace_id,
                timeout_seconds=timeout,
            )

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        cfgs = list_mcp_servers(self._workspace_id)
        if not cfgs:
            return

        async def _one(cfg: MCPServerConfig) -> None:
            try:
                await self._connect_timed(cfg)
            except Exception as exc:
                self._last_errors[cfg.name] = str(exc)
                log.error(
                    "mcp_connect_failed",
                    server=cfg.name,
                    workspace_id=self._workspace_id,
                    error=str(exc),
                )

        await asyncio.gather(*[_one(cfg) for cfg in cfgs], return_exceptions=True)

    async def _connect(self, cfg: MCPServerConfig) -> None:
        if cfg.name in self._sessions:
            return
        stack = AsyncExitStack()
        try:
            if cfg.transport == "stdio":
                params = StdioServerParameters(
                    command=cfg.command[0] if cfg.command else "",
                    args=cfg.command[1:] + cfg.args if len(cfg.command) > 1 else cfg.args,
                    env=_stdio_env(cfg, self._workspace_id),
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif cfg.transport == "http":
                if not cfg.url:
                    raise ValueError("http transport requires url")
                if cfg.auth == "oauth":
                    session = await connect_http_oauth_session(
                        stack,
                        server_name=cfg.name,
                        server_url=cfg.url,
                        workspace_id=self._workspace_id,
                    )
                    self._sessions[cfg.name] = session
                    self._stacks[cfg.name] = stack
                    await self._register_tools(cfg.name, session)
                    log.info(
                        "mcp_connected",
                        server=cfg.name,
                        workspace_id=self._workspace_id,
                        transport=cfg.transport,
                        auth="oauth",
                    )
                    return
                transport = await stack.enter_async_context(streamablehttp_client(cfg.url))
                read, write, _ = transport
            else:
                raise ValueError(f"unknown transport: {cfg.transport}")

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[cfg.name] = session
            self._stacks[cfg.name] = stack
            await self._register_tools(cfg.name, session)
            log.info(
                "mcp_connected",
                server=cfg.name,
                workspace_id=self._workspace_id,
                transport=cfg.transport,
            )
        except BaseException:
            await self._discard_connect_state(cfg.name, stack)
            raise

    async def _register_tools(self, server_name: str, session: ClientSession) -> None:
        async with self._tools_lock:
            listed = await session.list_tools()
            names: list[str] = []
            catalog: list[dict[str, Any]] = []
            category = mcp_tool_category(server_name, self._workspace_id)
            for tool_def in listed.tools:
                full_name = mcp_tool_full_name(server_name, tool_def.name, self._workspace_id)
                description = tool_def.description or f"MCP tool {tool_def.name}@{server_name}"
                schema = tool_def.inputSchema or {"type": "object", "properties": {}}
                schema_summary = _schema_summary(schema)

                async def _handler(
                    args: dict[str, Any],
                    _server=server_name,
                    _name=tool_def.name,
                    _mgr=self,
                ) -> ToolResult:
                    try:
                        result = await _mgr._call_tool_with_retry(_server, _name, args)
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
                        category=category,
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
            log.info(
                "mcp_tools_registered",
                server=server_name,
                workspace_id=self._workspace_id,
                count=len(listed.tools),
            )

    async def publish_tools_to_registry(self) -> None:
        """把当前已连接 MCP session 的工具挂到全局 registry（含启动预热与对话前同步）。"""
        for server_name in list(self._sessions.keys()):
            session = self._sessions.get(server_name)
            if session is None:
                continue
            try:
                await self._register_tools(server_name, session)
            except Exception as exc:
                log.warning(
                    "mcp_register_tools_failed",
                    server=server_name,
                    workspace_id=self._workspace_id,
                    error=str(exc) or repr(exc),
                )
                cfg = get_mcp_server(server_name, self._workspace_id)
                if cfg is None:
                    await self.remove_server(server_name)
                    continue
                runtime = await self.reconnect_server(server_name)
                if not runtime.get("connected"):
                    log.warning(
                        "mcp_reconnect_after_register_failed",
                        server=server_name,
                        workspace_id=self._workspace_id,
                        error=runtime.get("error"),
                    )

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
                workspace_id=self._workspace_id,
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
                    workspace_id=self._workspace_id,
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
                    workspace_id=self._workspace_id,
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
                workspace_id=self._workspace_id,
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
                workspace_id=self._workspace_id,
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
        except (OAuthRequiredError, asyncio.CancelledError) as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            log.warning(
                "mcp_oauth_required",
                server=cfg.name,
                workspace_id=self._workspace_id,
            )
            self._last_errors[cfg.name] = str(exc)
            return {
                "name": cfg.name,
                "connected": False,
                "tools": [],
                "error": str(exc),
            }
        except Exception as exc:
            log.error(
                "mcp_runtime_add_failed",
                server=cfg.name,
                workspace_id=self._workspace_id,
                error=str(exc),
            )
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
        cfg = get_mcp_server(server_name, self._workspace_id)
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
                    env=_stdio_env(cfg, self._workspace_id),
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif cfg.transport == "http":
                if not cfg.url:
                    raise ValueError("http transport requires url")
                if cfg.auth == "oauth":
                    result = await probe_http_oauth(
                        server_name=cfg.name,
                        server_url=cfg.url,
                        workspace_id=self._workspace_id,
                    )
                    if not result.get("connected"):
                        err = result.get("error") or "connection failed"
                        return {"name": cfg.name, "connected": False, "tools": [], "error": err}
                    oauth_stack = AsyncExitStack()
                    try:
                        session = await connect_http_oauth_session(
                            oauth_stack,
                            server_name=cfg.name,
                            server_url=cfg.url,
                            workspace_id=self._workspace_id,
                        )
                        listed = await session.list_tools()
                        tools = [
                            {
                                "name": t.name,
                                "full_name": mcp_tool_full_name(cfg.name, t.name, self._workspace_id),
                                "description": t.description or f"MCP tool {t.name}@{cfg.name}",
                                "input_schema": t.inputSchema or {"type": "object", "properties": {}},
                                "schema_summary": _schema_summary(
                                    t.inputSchema or {"type": "object", "properties": {}}
                                ),
                            }
                            for t in listed.tools
                        ]
                        return {"name": cfg.name, "connected": True, "tools": tools, "error": None}
                    finally:
                        await oauth_stack.aclose()
                else:
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
                    "full_name": mcp_tool_full_name(cfg.name, t.name, self._workspace_id),
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
        tool_names: list[str] = []
        async with self._tools_lock:
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
                log.warning(
                    "mcp_server_close_error",
                    server=server_name,
                    workspace_id=self._workspace_id,
                    error=str(exc),
                )
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
        for server_name in list(
            self._sessions.keys() | self._stacks.keys() | self._registered_tool_names.keys()
        ):
            await self.remove_server(server_name)
        self._registered_tool_names.clear()
        self._tool_catalog.clear()
        self._sessions.clear()
        self._stacks.clear()
        self._reconnect_locks.clear()
        self._last_errors.clear()
        self._started = False


_managers: dict[str, MCPManager] = {}


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


async def _get_or_create_manager(workspace_id: str) -> MCPManager:
    wid = normalize_workspace_id(workspace_id)
    async with _managers_lock:
        mgr = _managers.get(wid)
        if mgr is None:
            mgr = MCPManager(wid)
            _managers[wid] = mgr
        return mgr


async def ensure_mcp_started(workspace_id: str) -> MCPManager:
    mgr = await _get_or_create_manager(workspace_id)
    if not mgr._started:
        await mgr.start()
    return mgr


async def sync_mcp_tools_for_workspace(workspace_id: str) -> None:
    """注册当前工作区 MCP 工具（全局唯一命名）；LLM schema 由 registry 按 ContextVar 过滤。"""
    wid = normalize_workspace_id(workspace_id)
    mgr = await ensure_mcp_started(wid)
    await mgr.publish_tools_to_registry()


async def start_mcp() -> None:
    await ensure_mcp_started(get_workspace_id())


async def stop_mcp() -> None:
    await stop_all_mcp()


async def stop_all_mcp() -> None:
    async with _managers_lock:
        managers = list(_managers.values())
        _managers.clear()
    for mgr in managers:
        await mgr.stop()


async def connect_mcp_server(cfg: MCPServerConfig) -> dict[str, Any]:
    mgr = await ensure_mcp_started(get_workspace_id())
    return await mgr.add_server(cfg)


async def disconnect_mcp_server(server_name: str) -> bool:
    mgr = await _get_or_create_manager(get_workspace_id())
    return await mgr.remove_server(server_name)


def list_mcp_runtime() -> dict[str, dict[str, Any]]:
    wid = get_workspace_id()
    mgr = _managers.get(wid)
    if mgr is None:
        return {}
    return mgr.runtime_servers()


async def reconnect_mcp_server(server_name: str) -> dict[str, Any]:
    mgr = await ensure_mcp_started(get_workspace_id())
    return await mgr.reconnect_server(server_name)


async def probe_mcp_server(cfg: MCPServerConfig) -> dict[str, Any]:
    mgr = await _get_or_create_manager(get_workspace_id())
    return await mgr.probe_server(cfg)


async def reconnect_all_mcp_servers_for_workspace(workspace_id: str) -> dict[str, Any]:
    mgr = await ensure_mcp_started(workspace_id)
    results: dict[str, Any] = {}
    for cfg in list_mcp_servers(workspace_id):
        results[cfg.name] = await mgr.reconnect_server(cfg.name)
    return results


async def reconnect_all_mcp_servers() -> dict[str, Any]:
    from ..workspace import iter_workspace_ids, set_workspace_id

    all_results: dict[str, Any] = {}
    for wid in iter_workspace_ids():
        set_workspace_id(wid)
        all_results[wid] = await reconnect_all_mcp_servers_for_workspace(wid)
    return all_results
