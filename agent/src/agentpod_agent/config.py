"""容器内 Agent 配置。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    internal_token: str = Field(default="", alias="INTERNAL_TOKEN")
    user_id: str = Field(default="", alias="USER_ID")

    llm_base_url: str = Field(
        default="http://127.0.0.1:8080/internal/llm/v1",
        alias="LLM_BASE_URL",
    )

    embedding_base_url: str = Field(default="http://tei:80", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", alias="EMBEDDING_MODEL")

    host_internal_url: str = Field(default="", alias="HOST_INTERNAL_URL")

    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    shared_skills_dir: Path = Field(default=Path("/app/skills"), alias="SHARED_SKILLS_DIR")
    attachment_storage: str = Field(default="minio", alias="ATTACHMENT_STORAGE")

    max_loop_rounds: int = Field(default=20, alias="MAX_LOOP_ROUNDS")
    max_tool_rounds: int = Field(default=30, alias="MAX_TOOL_ROUNDS")
    context_compress_ratio: float = Field(default=0.8, alias="CONTEXT_COMPRESS_RATIO")
    full_inject_threshold: int = Field(default=20, alias="FULL_INJECT_THRESHOLD")

    # 上下文压缩蒸馏：保留最近 N 条；中间段被摘要而非直接丢弃
    context_keep_last: int = Field(default=8, alias="CONTEXT_KEEP_LAST")
    context_distill_min_middle: int = Field(default=4, alias="CONTEXT_DISTILL_MIN_MIDDLE")

    # 技能自我改进：本轮工具调用数达到阈值才触发任务后反思沉淀
    skill_reflect_min_tool_calls: int = Field(default=5, alias="SKILL_REFLECT_MIN_TOOL_CALLS")

    # 记忆策展：总条数超过上限触发一次 LLM 去重/合并/淘汰
    memory_max_items: int = Field(default=200, alias="MEMORY_MAX_ITEMS")
    memory_curate_batch: int = Field(default=60, alias="MEMORY_CURATE_BATCH")

    # 写入安全门：是否启用（LLM 语义审查为主）
    write_guard_enabled: bool = Field(default=True, alias="WRITE_GUARD_ENABLED")

    # 向量召回：余弦距离上限（距离越小越相关），超过则视为不相关丢弃
    recall_max_distance: float = Field(default=0.6, alias="RECALL_MAX_DISTANCE")

    # MCP 工具调用超时（秒）：避免上游插件异常时调用长期挂起
    mcp_call_timeout_seconds: float = Field(default=45.0, alias="MCP_CALL_TIMEOUT_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
