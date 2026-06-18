"""宿主全局配置（settings.json 驱动）。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    mcp_oauth_redirect_uri: str = Field(
        default="http://localhost/api/oauth/mcp/callback",
        alias="MCP_OAUTH_REDIRECT_URI",
    )

    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")
    session_secret: str = Field(default="", alias="SESSION_SECRET")

    host_sqlite_path: str = Field(default="", alias="HOST_SQLITE_PATH")

    agent_service_url: str = Field(default="http://127.0.0.1:21223", alias="AGENT_SERVICE_URL")
    agent_internal_token: str = Field(default="", alias="AGENT_INTERNAL_TOKEN")
    enable_terminal: bool = Field(default=True, alias="ENABLE_TERMINAL")
    terminal_whitelist: str = Field(default="git,npm,node,python3,make", alias="TERMINAL_WHITELIST")
    terminal_denylist: str = Field(default="sh,bash,zsh,dash,fish", alias="TERMINAL_DENYLIST")
    terminal_restrict_workspace: bool = Field(default=True, alias="TERMINAL_RESTRICT_WORKSPACE")
    sandbox_max_memory_mb: int = Field(default=512, alias="SANDBOX_MAX_MEMORY_MB")
    sandbox_max_cpu_seconds: int = Field(default=20, alias="SANDBOX_MAX_CPU_SECONDS")
    sandbox_max_processes: int = Field(default=64, alias="SANDBOX_MAX_PROCESSES")
    sandbox_max_open_files: int = Field(default=256, alias="SANDBOX_MAX_OPEN_FILES")
    sandbox_max_file_mb: int = Field(default=16, alias="SANDBOX_MAX_FILE_MB")
    sandbox_kill_grace_seconds: float = Field(default=2.0, alias="SANDBOX_KILL_GRACE_SECONDS")

    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    auxiliary_vision_model: str = Field(default="", alias="AUXILIARY_VISION_MODEL")
    auxiliary_web_extract_model: str = Field(default="", alias="AUXILIARY_WEB_EXTRACT_MODEL")
    auxiliary_compression_model: str = Field(default="", alias="AUXILIARY_COMPRESSION_MODEL")
    auxiliary_title_generation_model: str = Field(
        default="", alias="AUXILIARY_TITLE_GENERATION_MODEL"
    )
    auxiliary_approval_model: str = Field(default="", alias="AUXILIARY_APPROVAL_MODEL")
    auxiliary_curator_model: str = Field(default="", alias="AUXILIARY_CURATOR_MODEL")
    auxiliary_skill_reflect_model: str = Field(default="", alias="AUXILIARY_SKILL_REFLECT_MODEL")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    jina_api_key: str = Field(default="", alias="JINA_API_KEY")

    embedding_base_url: str = Field(default="local", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", alias="EMBEDDING_MODEL")
    attachment_max_bytes: int = Field(default=25 * 1024 * 1024, alias="ATTACHMENT_MAX_BYTES")
    attachment_storage: str = Field(default="local", alias="ATTACHMENT_STORAGE")

    internal_network_guard_enabled: bool = Field(default=True, alias="INTERNAL_NETWORK_GUARD_ENABLED")
    internal_allowed_cidrs: str = Field(
        default="127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
        alias="INTERNAL_ALLOWED_CIDRS",
    )
    internal_rate_limit_per_minute: int = Field(default=120, alias="INTERNAL_RATE_LIMIT_PER_MINUTE")
    attachment_delete_max_keys: int = Field(default=100, alias="ATTACHMENT_DELETE_MAX_KEYS")

    scheduled_task_retry_max_attempts: int = Field(default=3, alias="SCHEDULED_TASK_RETRY_MAX_ATTEMPTS")
    scheduled_task_retry_initial_delay_seconds: float = Field(
        default=2.0, alias="SCHEDULED_TASK_RETRY_INITIAL_DELAY_SECONDS"
    )
    scheduled_task_retry_max_delay_seconds: float = Field(
        default=30.0, alias="SCHEDULED_TASK_RETRY_MAX_DELAY_SECONDS"
    )
    scheduled_task_retry_backoff_multiplier: float = Field(
        default=2.0, alias="SCHEDULED_TASK_RETRY_BACKOFF_MULTIPLIER"
    )

    background_review_enabled: bool = Field(default=True, alias="BACKGROUND_REVIEW_ENABLED")
    background_review_memory_nudge_turns: int = Field(default=20, alias="BACKGROUND_REVIEW_MEMORY_NUDGE_TURNS")
    background_review_skill_nudge_loop_rounds: int = Field(
        default=24, alias="BACKGROUND_REVIEW_SKILL_NUDGE_LOOP_ROUNDS"
    )
    background_review_max_rounds: int = Field(default=4, alias="BACKGROUND_REVIEW_MAX_ROUNDS")

    mcp_call_timeout_seconds: float = Field(default=45.0, alias="MCP_CALL_TIMEOUT_SECONDS")
    mcp_connect_timeout_seconds: float = Field(default=30.0, alias="MCP_CONNECT_TIMEOUT_SECONDS")
    mcp_reconnect_delay_seconds: float = Field(default=5.0, alias="MCP_RECONNECT_DELAY_SECONDS")
    mcp_reconnect_interval_seconds: float = Field(default=60.0, alias="MCP_RECONNECT_INTERVAL_SECONDS")

    public_base_url: str = Field(default="http://localhost", alias="PUBLIC_BASE_URL")


@lru_cache
def get_settings() -> Settings:
    from agentpod_shared.settings_store import document_to_host_kwargs

    kwargs = document_to_host_kwargs()
    return Settings.model_construct(**kwargs)
