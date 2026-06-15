"""MCP 客户端：按工作区隔离 manager，工具注册带 workspace 前缀 category。"""

from __future__ import annotations

import asyncio
import shutil
import time
from contextlib import AsyncExitStack
from typing import Any
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..config import get_settings
from ..db import run_in_thread
from ..logging import get_logger
from ..tool_settings import is_mcp_server_enabled
from ..tools import Tool, ToolError, ToolResult
from ..tools import registry as tool_registry
from ..workspace import (
    get_workspace_id,
    mcp_tool_category,
    mcp_tool_full_name,
    normalize_workspace_id,
    set_workspace_id,
    workspace_data_dir,
)
from .config import MCPServerConfig, get_mcp_server, list_mcp_servers
from .oauth import OAuthRequiredError, connect_http_oauth_session

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


def _prepare_stdio_connect(cfg: MCPServerConfig, workspace_id: str) -> None:
    command = cfg.command or []
    if command and command[0] == "npx":
        npx_cache = workspace_data_dir(workspace_id) / ".npm-cache" / "_npx"
        if npx_cache.is_dir():
            shutil.rmtree(npx_cache, ignore_errors=True)


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
        except TimeoutError as exc:
            await self.remove_server(cfg.name)
            msg = f"connect timeout after {timeout}s"
            self._last_errors[cfg.name] = msg
            log.error(
                "mcp_connect_timeout",
                server=cfg.name,
                workspace_id=self._workspace_id,
                timeout_seconds=timeout,
            )
            raise TimeoutError(msg) from exc

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        cfgs = await run_in_thread(list_mcp_servers, self._workspace_id)
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

    async def reconnect_missing_servers(self) -> int:
        """连接 mcp.yaml 中已配置但当前无 session 的服务；返回新连上的数量。"""
        if not self._started:
            await self.start()
            return len(self._sessions)

        cfgs = await run_in_thread(list_mcp_servers, self._workspace_id)
        missing = [cfg for cfg in cfgs if cfg.name not in self._sessions]
        if not missing:
            return 0

        reconnected: list[str] = []

        async def _one(cfg: MCPServerConfig) -> None:
            if cfg.name in self._sessions:
                return
            try:
                await self._connect_timed(cfg)
            except Exception as exc:
                self._last_errors[cfg.name] = str(exc)
                log.warning(
                    "mcp_reconnect_missing_failed",
                    server=cfg.name,
                    workspace_id=self._workspace_id,
                    error=str(exc),
                )
                return
            if cfg.name in self._sessions:
                reconnected.append(cfg.name)

        await asyncio.gather(*[_one(cfg) for cfg in missing], return_exceptions=True)
        if reconnected:
            log.info(
                "mcp_missing_reconnected",
                workspace_id=self._workspace_id,
                servers=reconnected,
                count=len(reconnected),
            )
        return len(reconnected)

    async def _connect(self, cfg: MCPServerConfig) -> None:
        if cfg.name in self._sessions:
            return
        stack = AsyncExitStack()
        try:
            if cfg.transport == "stdio":
                await run_in_thread(_prepare_stdio_connect, cfg, self._workspace_id)
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
                transport = await stack.enter_async_context(
                    streamablehttp_client(cfg.url, headers=dict(cfg.headers or {}))
                )
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

    async def _list_tools_timed(self, server_name: str, session: ClientSession):
        timeout = max(1.0, float(get_settings().mcp_call_timeout_seconds))
        try:
            return await asyncio.wait_for(session.list_tools(), timeout=timeout)
        except TimeoutError as exc:
            msg = f"list_tools timeout after {timeout:.1f}s"
            self._last_errors[server_name] = msg
            raise TimeoutError(f"{server_name}: {msg}") from exc

    async def _register_tools(self, server_name: str, session: ClientSession) -> None:
        listed = await self._list_tools_timed(server_name, session)
        catalog: list[dict[str, Any]] = []
        for tool_def in listed.tools:
            full_name = mcp_tool_full_name(server_name, tool_def.name, self._workspace_id)
            description = tool_def.description or f"MCP tool {tool_def.name}@{server_name}"
            schema = tool_def.inputSchema or {"type": "object", "properties": {}}
            catalog.append(
                {
                    "name": tool_def.name,
                    "full_name": full_name,
                    "description": description,
                    "input_schema": schema,
                    "schema_summary": _schema_summary(schema),
                }
            )
        async with self._tools_lock:
            names = self._apply_catalog_to_registry(server_name, catalog)
            self._registered_tool_names[server_name] = names
            self._tool_catalog[server_name] = catalog
        log.info(
            "mcp_tools_registered",
            server=server_name,
            workspace_id=self._workspace_id,
            count=len(catalog),
        )
        from ..activity import record_activity

        tool_names = [t["name"] for t in catalog[:12]]
        record_activity(
            "mcp",
            "tools_registered",
            f"「{server_name}」注册 {len(catalog)} 个工具",
            workspace_id=self._workspace_id,
            detail={"tool_count": len(catalog), "tools_preview": tool_names},
        )

    def _make_mcp_handler(self, server_name: str, tool_name: str):
        async def _handler(
            args: dict[str, Any],
            _server=server_name,
            _name=tool_name,
            _mgr=self,
        ) -> ToolResult:
            try:
                result = await _mgr._call_tool_with_retry(_server, _name, args)
            except Exception as exc:
                raise ToolError(f"mcp call failed: {exc}") from exc
            if getattr(result, "isError", False):
                raise ToolError(_extract_text(result))
            return ToolResult(content=_extract_text(result))

        return _handler

    def _apply_catalog_to_registry(self, server_name: str, catalog: list[dict[str, Any]]) -> list[str]:
        category = mcp_tool_category(server_name, self._workspace_id)
        enabled = is_mcp_server_enabled(server_name)
        names: list[str] = []
        for entry in catalog:
            full_name = str(entry.get("full_name") or "").strip()
            tool_name = str(entry.get("name") or "").strip()
            if not full_name or not tool_name:
                continue
            description = str(entry.get("description") or f"MCP tool {tool_name}@{server_name}")
            schema = entry.get("input_schema") or {"type": "object", "properties": {}}
            tool_registry.register(
                Tool(
                    name=full_name,
                    description=description,
                    parameters=schema,
                    handler=self._make_mcp_handler(server_name, tool_name),
                    enabled=enabled,
                    category=category,
                )
            )
            names.append(full_name)
        return names

    async def publish_tools_to_registry(self) -> None:
        """把当前已连接 MCP session 的工具挂到全局 registry（含启动预热与对话前同步）。"""
        for server_name in list(self._sessions.keys()):
            if server_name not in self._sessions:
                continue
            catalog = self._tool_catalog.get(server_name) or []
            if catalog:
                async with self._tools_lock:
                    names = self._apply_catalog_to_registry(server_name, catalog)
                    self._registered_tool_names[server_name] = names
                continue
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
                cfg = await run_in_thread(get_mcp_server, server_name, self._workspace_id)
                if cfg is None:
                    await self.remove_server(server_name)
                    continue
                if isinstance(exc, TimeoutError):
                    schedule_mcp_server_reconnect(self._workspace_id, server_name)
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
            await self._connect_timed(cfg)
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
        if cfg.name not in self._sessions:
            err = self._last_errors.get(cfg.name) or "connect failed"
            return {
                "name": cfg.name,
                "connected": False,
                "tools": [],
                "error": err,
            }
        self._last_errors.pop(cfg.name, None)
        return {
            "name": cfg.name,
            "connected": True,
            "tools": self._tool_catalog.get(cfg.name, []),
            "error": None,
        }

    async def reconnect_server(self, server_name: str) -> dict[str, Any]:
        cfg = await run_in_thread(get_mcp_server, server_name, self._workspace_id)
        if cfg is None:
            return {"name": server_name, "connected": False, "tools": [], "error": "server not found"}
        lock = self._reconnect_locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            await self.remove_server(server_name)
            if cfg.transport == "stdio":
                await run_in_thread(_prepare_stdio_connect, cfg, self._workspace_id)
            return await self.add_server(cfg)

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


async def ensure_mcp_manager(workspace_id: str) -> MCPManager:
    """获取 MCP manager，不触发全量连接（避免保存/重连单服时阻塞）。"""
    return await _get_or_create_manager(workspace_id)


async def ensure_mcp_started(workspace_id: str) -> MCPManager:
    mgr = await ensure_mcp_manager(workspace_id)
    if not mgr._started:
        await mgr.start()
    return mgr


async def sync_mcp_tools_for_workspace(workspace_id: str) -> None:
    """注册当前工作区 MCP 工具（全局唯一命名）；LLM schema 由 registry 按 ContextVar 过滤。"""
    wid = normalize_workspace_id(workspace_id)
    mgr = await ensure_mcp_started(wid)
    await mgr.reconnect_missing_servers()
    await mgr.publish_tools_to_registry()


_deferred_reconnect_inflight: set[tuple[str, str]] = set()
_connect_inflight: dict[tuple[str, str], asyncio.Task[None]] = {}


def _pending_runtime(name: str, *, message: str = "connect scheduled") -> dict[str, Any]:
    return {
        "name": name,
        "connected": False,
        "pending": True,
        "tools": [],
        "error": None,
        "message": message,
    }


async def _connect_mcp_server_task(workspace_id: str, cfg: MCPServerConfig) -> None:
    wid = normalize_workspace_id(workspace_id)
    set_workspace_id(wid)
    try:
        mgr = await ensure_mcp_manager(wid)
        runtime = await mgr.add_server(cfg)
        if runtime.get("connected"):
            await mgr.publish_tools_to_registry()
            from ..workspace_runtime import mark_mcp_runtime_ready

            mark_mcp_runtime_ready(wid)
            log.info("mcp_background_connect_ok", server=cfg.name, workspace_id=wid)
            from ..activity import record_activity

            tool_count = len(runtime.get("tools") or [])
            record_activity(
                "mcp",
                "connect",
                f"「{cfg.name}」连接成功，{tool_count} 个工具",
                workspace_id=wid,
                detail={"transport": cfg.transport, "tool_count": tool_count},
            )
        else:
            log.warning(
                "mcp_background_connect_failed",
                server=cfg.name,
                workspace_id=wid,
                error=runtime.get("error"),
            )
            from ..activity import record_activity

            record_activity(
                "mcp",
                "connect",
                f"「{cfg.name}」连接失败：{runtime.get('error') or 'unknown'}",
                workspace_id=wid,
                level="error",
                detail={"transport": cfg.transport},
            )
    except Exception as exc:
        log.warning(
            "mcp_background_connect_error",
            server=cfg.name,
            workspace_id=wid,
            error=str(exc),
        )
        from ..activity import record_activity

        record_activity(
            "mcp",
            "connect",
            f"「{cfg.name}」连接异常：{exc}",
            workspace_id=wid,
            level="error",
        )


def schedule_mcp_server_connect(workspace_id: str, cfg: MCPServerConfig) -> dict[str, Any]:
    """保存配置后后台连接，避免阻塞对话/API 请求。"""
    wid = normalize_workspace_id(workspace_id)
    name = str(cfg.name or "").strip()
    if not name:
        return {"name": "", "connected": False, "tools": [], "error": "name is required"}
    key = (wid, name)
    existing = _connect_inflight.get(key)
    if existing is not None and not existing.done():
        return _pending_runtime(name, message="connect already in progress")

    async def _run() -> None:
        try:
            await _connect_mcp_server_task(wid, cfg)
        finally:
            _connect_inflight.pop(key, None)

    _connect_inflight[key] = asyncio.create_task(_run(), name=f"mcp-connect-{name}")
    return _pending_runtime(name)


async def _refresh_mcp_server_task(workspace_id: str, server_name: str) -> None:
    from ..workspace_runtime import refresh_mcp_server

    await refresh_mcp_server(workspace_id, server_name)


def schedule_mcp_server_refresh(workspace_id: str, server_name: str) -> dict[str, Any]:
    """后台重连单服，避免阻塞对话/API 请求。"""
    wid = normalize_workspace_id(workspace_id)
    name = str(server_name or "").strip()
    if not name:
        return {"name": "", "connected": False, "tools": [], "error": "name is required"}
    key = (wid, name)
    existing = _connect_inflight.get(key)
    if existing is not None and not existing.done():
        return _pending_runtime(name, message="reconnect already in progress")

    async def _run() -> None:
        try:
            await _refresh_mcp_server_task(wid, name)
        finally:
            _connect_inflight.pop(key, None)

    _connect_inflight[key] = asyncio.create_task(_run(), name=f"mcp-refresh-{name}")
    return _pending_runtime(name, message="reconnect scheduled")


async def _deferred_reconnect_server(workspace_id: str, server_name: str) -> None:
    delay = max(0.0, float(get_settings().mcp_reconnect_delay_seconds))
    if delay > 0:
        await asyncio.sleep(delay)
    wid = normalize_workspace_id(workspace_id)
    mgr = await _get_or_create_manager(wid)
    if server_name in mgr._sessions:
        return
    cfg = await run_in_thread(get_mcp_server, server_name, wid)
    if cfg is None:
        return
    runtime = await mgr.reconnect_server(server_name)
    if runtime.get("connected"):
        await mgr.publish_tools_to_registry()
        from ..workspace_runtime import mark_mcp_runtime_ready

        mark_mcp_runtime_ready(wid)
        log.info("mcp_deferred_reconnect_ok", server=server_name, workspace_id=wid)
    else:
        log.warning(
            "mcp_deferred_reconnect_failed",
            server=server_name,
            workspace_id=wid,
            error=runtime.get("error"),
        )


def schedule_mcp_server_reconnect(workspace_id: str, server_name: str) -> None:
    """list_tools 超时等踢掉服务后，延迟一次后台重连。"""
    wid = normalize_workspace_id(workspace_id)
    name = str(server_name or "").strip()
    if not name:
        return
    key = (wid, name)
    if key in _deferred_reconnect_inflight:
        return
    _deferred_reconnect_inflight.add(key)

    async def _run() -> None:
        try:
            await _deferred_reconnect_server(wid, name)
        except Exception as exc:
            log.warning(
                "mcp_deferred_reconnect_error",
                server=name,
                workspace_id=wid,
                error=str(exc),
            )
        finally:
            _deferred_reconnect_inflight.discard(key)

    asyncio.create_task(_run(), name=f"mcp-reconnect-{name}")


async def reconnect_missing_mcp_servers(workspace_id: str) -> int:
    """补连配置中存在但未在线的 MCP；有新连接时同步工具注册。"""
    wid = normalize_workspace_id(workspace_id)
    mgr = await ensure_mcp_started(wid)
    count = await mgr.reconnect_missing_servers()
    if count > 0:
        await mgr.publish_tools_to_registry()
        from ..workspace_runtime import mark_mcp_runtime_ready

        mark_mcp_runtime_ready(wid)
    return count


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
    mgr = await ensure_mcp_manager(get_workspace_id())
    return await mgr.add_server(cfg)


async def disconnect_mcp_server(server_name: str) -> bool:
    mgr = await _get_or_create_manager(get_workspace_id())
    return await mgr.remove_server(server_name)


def list_mcp_runtime() -> dict[str, dict[str, Any]]:
    wid = get_workspace_id()
    mgr = _managers.get(wid)
    out: dict[str, dict[str, Any]] = mgr.runtime_servers() if mgr is not None else {}
    for (workspace_id, name), task in _connect_inflight.items():
        if workspace_id != wid or task.done():
            continue
        entry = out.setdefault(name, {"connected": False, "tools": [], "error": None})
        entry["pending"] = True
    return out


async def reconnect_mcp_server(server_name: str) -> dict[str, Any]:
    mgr = await ensure_mcp_manager(get_workspace_id())
    return await mgr.reconnect_server(server_name)
