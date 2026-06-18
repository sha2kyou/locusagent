"""Tool 基础协议 + 内置工具自动收集。

每个 tool 是一个 dataclass：name / description / parameters(JSON Schema) / handler。
内置工具在各模块定义后通过 `register_builtin` 集中收集。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


class ToolError(RuntimeError):
    """工具执行失败：会被 dispatch 包装为 tool message 回灌 LLM，不返回 5xx。"""


@dataclass(slots=True)
class ToolResult:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> str:
        return self.content


Handler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    enabled: bool = True
    category: str = "builtin"
    strict_schema: bool = False

    def to_openai_schema(self) -> dict[str, Any]:
        params = dict(self.parameters)
        if self.strict_schema:
            params.setdefault("additionalProperties", False)
        fn: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }
        if self.strict_schema:
            fn["strict"] = True
        return {"type": "function", "function": fn}


_BUILTINS: list[Tool] = []


def register_builtin(tool: Tool) -> Tool:
    _BUILTINS.append(tool)
    return tool


def builtin_tools() -> list[Tool]:
    return list(_BUILTINS)
