"""Tool 注册中心：内置 + MCP 工具统一通过此处分发。"""

from __future__ import annotations

import threading
from typing import Any

from ..logging import get_logger
from ..workspace import mcp_tool_category_prefix
from .base import Tool, ToolError, ToolResult, builtin_tools

log = get_logger("tools")


def _tool_visible_in_workspace(tool: Tool, workspace_id: str | None = None) -> bool:
    if not tool.category.startswith("mcp:"):
        return True
    prefix = mcp_tool_category_prefix(workspace_id)
    return tool.category.startswith(prefix)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._lock = threading.RLock()
        with self._lock:
            for tool in builtin_tools():
                self._tools[tool.name] = tool

    def register(self, tool: Tool) -> None:
        with self._lock:
            if tool.name in self._tools:
                log.warning("tool_overwritten", name=tool.name)
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        with self._lock:
            self._tools.pop(name, None)

    def unregister_mcp_tools_outside_workspace(self, workspace_id: str | None = None) -> int:
        """切换工作区时移除其他工作区的 MCP 工具，避免全局 registry 堆积。"""
        from ..workspace import mcp_tool_category_prefix

        prefix = mcp_tool_category_prefix(workspace_id)
        with self._lock:
            stale = [
                name
                for name, tool in self._tools.items()
                if tool.category.startswith("mcp:") and not tool.category.startswith(prefix)
            ]
            for name in stale:
                self._tools.pop(name, None)
        return len(stale)

    def get(self, name: str) -> Tool | None:
        with self._lock:
            return self._tools.get(name)

    def list(self, *, workspace_id: str | None = None) -> list[Tool]:
        with self._lock:
            tools = list(self._tools.values())
        return [t for t in tools if t.enabled and _tool_visible_in_workspace(t, workspace_id)]

    def all(self) -> list[Tool]:
        with self._lock:
            return list(self._tools.values())

    def set_enabled(self, name: str, enabled: bool) -> bool:
        with self._lock:
            tool = self._tools.get(name)
            if tool is None:
                return False
            tool.enabled = enabled
            return True

    def schemas(self, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self.list(workspace_id=workspace_id)]

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        with self._lock:
            tool = self._tools.get(name)
            enabled = tool.enabled if tool is not None else False
        if tool is None:
            raise ToolError(f"unknown tool: {name}")
        if not enabled:
            raise ToolError(f"tool disabled: {name}")
        try:
            return await tool.handler(args)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc


registry = ToolRegistry()
