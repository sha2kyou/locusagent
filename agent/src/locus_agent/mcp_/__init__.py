"""MCP 客户端：stdio + HTTP transport，发现 tools 后注册到 ToolRegistry。"""

"""MCP 模块：仅 config 默认导出；client 按需 import 以避免循环。"""

from .config import (
    MCPServerConfig,
    add_mcp_server,
    get_mcp_server,
    list_mcp_servers,
    load_mcp_config,
    remove_mcp_server,
    update_mcp_server,
)

__all__ = [
    "MCPServerConfig",
    "add_mcp_server",
    "get_mcp_server",
    "list_mcp_servers",
    "load_mcp_config",
    "remove_mcp_server",
    "update_mcp_server",
]
