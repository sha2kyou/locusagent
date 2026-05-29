"""Tool 注册中心：内置 + MCP 工具统一通过此处分发。"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger
from .base import Tool, ToolError, ToolResult, builtin_tools

log = get_logger("tools")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in builtin_tools():
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            log.warning("tool_overwritten", name=tool.name)
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.enabled]

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def set_enabled(self, name: str, enabled: bool) -> bool:
        tool = self._tools.get(name)
        if tool is None:
            return False
        tool.enabled = enabled
        return True

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self.list()]

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool: {name}")
        if not tool.enabled:
            raise ToolError(f"tool disabled: {name}")
        try:
            return await tool.handler(args)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc


registry = ToolRegistry()
