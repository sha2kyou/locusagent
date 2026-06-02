"""Agent 容器环境变量：仅内部令牌与非密钥配置。

平台凭据与上游配置（LLM API Key、Tavily/Jina、模型角色映射等）留在 Host，
由 /internal/* 代理；不得写入 user pod 环境变量。
"""

from __future__ import annotations

from ..config import Settings, get_settings


def require_llm_configured(settings: Settings | None = None) -> None:
    s = settings or get_settings()
    if not s.llm_api_key.strip():
        raise RuntimeError("LLM_API_KEY 未配置，请在宿主 .env 中设置")


def build_agent_environment(
    *,
    user_id: int,
    internal_token: str,
    llm_proxy_base_url: str,
    embedding_base_url: str,
    embedding_model: str,
    host_internal_url: str,
    attachment_storage: str,
    enable_terminal: bool,
    terminal_whitelist: str,
    settings: Settings | None = None,
) -> dict[str, str]:
    s = settings or get_settings()
    require_llm_configured(s)
    env: dict[str, str] = {
        "LLM_BASE_URL": llm_proxy_base_url,
        "USER_ID": str(user_id),
        "INTERNAL_TOKEN": internal_token,
        "EMBEDDING_BASE_URL": embedding_base_url,
        "EMBEDDING_MODEL": embedding_model,
        "HOST_INTERNAL_URL": host_internal_url,
        "ATTACHMENT_STORAGE": attachment_storage,
        "ENABLE_TERMINAL": "1" if enable_terminal else "0",
        "TERMINAL_WHITELIST": terminal_whitelist,
        "TERMINAL_DENYLIST": s.terminal_denylist,
        "TERMINAL_RESTRICT_WORKSPACE": "1" if s.terminal_restrict_workspace else "0",
        "SANDBOX_MAX_MEMORY_MB": str(s.sandbox_max_memory_mb),
        "SANDBOX_MAX_CPU_SECONDS": str(s.sandbox_max_cpu_seconds),
        "SANDBOX_MAX_PROCESSES": str(s.sandbox_max_processes),
        "SANDBOX_MAX_OPEN_FILES": str(s.sandbox_max_open_files),
        "SANDBOX_MAX_FILE_MB": str(s.sandbox_max_file_mb),
        "SANDBOX_KILL_GRACE_SECONDS": str(s.sandbox_kill_grace_seconds),
    }
    return env
