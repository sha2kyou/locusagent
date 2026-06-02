"""宿主全局配置（环境变量驱动）。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    github_client_id: str = Field(default="", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", alias="GITHUB_CLIENT_SECRET")
    oauth_redirect_uri: str = Field(
        default="http://localhost/api/oauth/github/callback",
        alias="OAUTH_REDIRECT_URI",
    )
    mcp_oauth_redirect_uri: str = Field(
        default="http://localhost/api/oauth/mcp/callback",
        alias="MCP_OAUTH_REDIRECT_URI",
    )

    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")
    session_secret: str = Field(default="", alias="SESSION_SECRET")

    database_url: str = Field(
        default="postgresql+asyncpg://agentpod:agentpod-dev-password@localhost:5432/agentpod",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    docker_host: str = Field(
        default="tcp://docker-proxy:2375",
        validation_alias=AliasChoices("AGENTPOD_DOCKER_HOST", "DOCKER_HOST"),
    )
    agent_image: str = Field(default="agentpod-agent:latest", alias="AGENT_IMAGE")
    enable_terminal: bool = Field(default=False, alias="ENABLE_TERMINAL")
    terminal_whitelist: str = Field(default="", alias="TERMINAL_WHITELIST")
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

    embedding_base_url: str = Field(default="http://tei:80", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", alias="EMBEDDING_MODEL")
    # 聊天附件大小上限（字节），默认 1MB。
    attachment_max_bytes: int = Field(default=1_048_576, alias="ATTACHMENT_MAX_BYTES")
    attachment_storage: str = Field(default="minio", alias="ATTACHMENT_STORAGE")
    s3_endpoint: str = Field(default="minio:9000", alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="agentpod-attachments", alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_use_ssl: bool = Field(default=False, alias="S3_USE_SSL")

    internal_network_guard_enabled: bool = Field(default=True, alias="INTERNAL_NETWORK_GUARD_ENABLED")
    internal_allowed_cidrs: str = Field(
        default="127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
        alias="INTERNAL_ALLOWED_CIDRS",
    )
    internal_rate_limit_per_minute: int = Field(default=120, alias="INTERNAL_RATE_LIMIT_PER_MINUTE")
    attachment_delete_max_keys: int = Field(default=100, alias="ATTACHMENT_DELETE_MAX_KEYS")

    agent_memory_limit: str = Field(default="512m", alias="AGENT_MEMORY_LIMIT")
    agent_cpu_quota: int = Field(default=50000, alias="AGENT_CPU_QUOTA")
    agent_pids_limit: int = Field(default=256, alias="AGENT_PIDS_LIMIT")
    # 每用户 /data 卷磁盘配额（如 "2g"）。空=不限。
    # 仅在宿主 docker 卷所在 FS 支持 project quota（XFS pquota / ext4 project）时可用。
    agent_disk_limit: str = Field(default="", alias="AGENT_DISK_LIMIT")

    idle_pause_seconds: int = Field(default=1800, alias="IDLE_PAUSE_SECONDS")
    pause_to_stop_seconds: int = Field(default=10800, alias="PAUSE_TO_STOP_SECONDS")
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

    public_base_url: str = Field(default="http://localhost", alias="PUBLIC_BASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
