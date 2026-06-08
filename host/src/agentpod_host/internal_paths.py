"""内部 API 路径分类（鉴权隔离 / 网络守卫）。"""

from __future__ import annotations

AGENT_INTERNAL_PREFIXES: tuple[str, ...] = (
    "/internal/llm",
    "/internal/tavily",
    "/internal/jina",
    "/internal/embedding",
    "/internal/attachments",
    "/internal/notifications",
    "/internal/scheduled-tasks",
    "/internal/settings",
    "/internal/usage",
    "/internal/mcp-oauth",
)


def is_agent_internal_path(path: str) -> bool:
    return any(path.startswith(p) for p in AGENT_INTERNAL_PREFIXES)


def is_internal_session_path(path: str) -> bool:
    return False
