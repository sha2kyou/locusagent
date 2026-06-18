"""工具系统：内置工具 + MCP 工具统一注册到 dispatch。

import 顺序：先 base，再各内置工具模块（注册副作用），最后 registry。
"""

from .base import Tool, ToolError, ToolResult, builtin_tools

# 触发各内置工具的 register_builtin 副作用
from . import locusagent as _locusagent  # noqa: F401
from . import artifacts as _artifacts  # noqa: F401
from . import clarify as _clarify  # noqa: F401
from . import context_distill as _summarize  # noqa: F401
from . import deliver_file as _deliver_file  # noqa: F401
from . import fs as _fs  # noqa: F401
from . import memory as _memory  # noqa: F401
from . import attachments as _attachments  # noqa: F401
from . import notifications as _notifications  # noqa: F401
from . import scheduled_tasks as _scheduled_tasks  # noqa: F401
from . import env_vars as _env_vars  # noqa: F401
from . import execute_code as _execute_code  # noqa: F401
from . import session_delete as _session_delete  # noqa: F401
from . import session_recall as _session_recall  # noqa: F401
from . import session_search as _session_search  # noqa: F401
from . import skills as _skills  # noqa: F401
from . import manage_workspace as _manage_workspace  # noqa: F401
from . import mcp_manage as _mcp_manage  # noqa: F401
from . import terminal as _terminal  # noqa: F401
from . import todo as _todo  # noqa: F401
from . import user_info as _user_info  # noqa: F401
from . import web as _web  # noqa: F401

from .registry import ToolRegistry, registry

__all__ = ["Tool", "ToolError", "ToolRegistry", "ToolResult", "builtin_tools", "registry"]
