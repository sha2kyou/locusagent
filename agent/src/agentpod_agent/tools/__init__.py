"""工具系统：内置工具 + MCP 工具统一注册到 dispatch。

import 顺序：先 base，再各内置工具模块（注册副作用），最后 registry。
"""

from .base import Tool, ToolError, ToolResult, builtin_tools

# 触发各内置工具的 register_builtin 副作用
from . import clarify as _clarify  # noqa: F401
from . import fs as _fs  # noqa: F401
from . import memory as _memory  # noqa: F401
from . import session_recall as _session_recall  # noqa: F401
from . import skills as _skills  # noqa: F401
from . import manage_workspace as _manage_workspace  # noqa: F401
from . import terminal as _terminal  # noqa: F401
from . import user_info as _user_info  # noqa: F401
from . import web as _web  # noqa: F401

from .registry import ToolRegistry, registry

__all__ = ["Tool", "ToolError", "ToolRegistry", "ToolResult", "builtin_tools", "registry"]
