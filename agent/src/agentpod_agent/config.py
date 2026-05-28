"""容器内 Agent 配置。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    internal_token: str = Field(default="", alias="INTERNAL_TOKEN")
    user_id: str = Field(default="", alias="USER_ID")

    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")

    embedding_base_url: str = Field(
        default="http://tei:80",
        validation_alias=AliasChoices("EMBEDDING_BASE_URL", "OLLAMA_BASE_URL"),
    )
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", alias="EMBEDDING_MODEL")

    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    shared_skills_dir: Path = Field(default=Path("/app/skills"), alias="SHARED_SKILLS_DIR")

    max_loop_rounds: int = Field(default=20, alias="MAX_LOOP_ROUNDS")
    max_tool_rounds: int = Field(default=30, alias="MAX_TOOL_ROUNDS")
    context_compress_ratio: float = Field(default=0.8, alias="CONTEXT_COMPRESS_RATIO")
    full_inject_threshold: int = Field(default=20, alias="FULL_INJECT_THRESHOLD")


@lru_cache
def get_settings() -> Settings:
    return Settings()
