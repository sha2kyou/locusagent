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

    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")
    session_secret: str = Field(default="", alias="SESSION_SECRET")

    database_url: str = Field(
        default="postgresql+asyncpg://agentpod:agentpod-dev-password@localhost:5432/agentpod",
        alias="DATABASE_URL",
    )

    docker_host: str = Field(default="unix:///var/run/docker.sock", alias="DOCKER_HOST")
    agent_image: str = Field(default="agentpod-agent:latest", alias="AGENT_IMAGE")
    enable_terminal: bool = Field(default=False, alias="ENABLE_TERMINAL")
    terminal_whitelist: str = Field(default="", alias="TERMINAL_WHITELIST")

    embedding_base_url: str = Field(
        default="http://tei:80",
        validation_alias=AliasChoices("EMBEDDING_BASE_URL", "OLLAMA_BASE_URL"),
    )
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", alias="EMBEDDING_MODEL")

    agent_memory_limit: str = Field(default="512m", alias="AGENT_MEMORY_LIMIT")
    agent_cpu_quota: int = Field(default=50000, alias="AGENT_CPU_QUOTA")
    agent_pids_limit: int = Field(default=256, alias="AGENT_PIDS_LIMIT")
    # 每用户 /data 卷磁盘配额（如 "2g"）。空=不限。
    # 仅在宿主 docker 卷所在 FS 支持 project quota（XFS pquota / ext4 project）时可用。
    agent_disk_limit: str = Field(default="", alias="AGENT_DISK_LIMIT")

    idle_pause_seconds: int = Field(default=1800, alias="IDLE_PAUSE_SECONDS")
    pause_to_stop_seconds: int = Field(default=86400, alias="PAUSE_TO_STOP_SECONDS")

    public_base_url: str = Field(default="http://localhost", alias="PUBLIC_BASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
