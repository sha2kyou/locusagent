"""内部 API 路径分类（鉴权隔离 / 网络守卫 / Caddy 同步）。"""

from __future__ import annotations

# 浏览器 Session 触发容器 provision
INTERNAL_SESSION_PREFIXES: tuple[str, ...] = ("/internal/containers",)

# Agent 容器 → Host 代理（Bearer 或 X-Internal-Token；不得经公网 Caddy）
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
)


def is_agent_internal_path(path: str) -> bool:
    return any(path.startswith(p) for p in AGENT_INTERNAL_PREFIXES)


def is_internal_session_path(path: str) -> bool:
    return any(path.startswith(p) for p in INTERNAL_SESSION_PREFIXES)
