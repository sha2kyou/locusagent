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

    # Background Self-Improvement Review（Hermes 对齐）
    background_review_enabled: bool = Field(default=True, alias="BACKGROUND_REVIEW_ENABLED")
    background_review_min_tool_calls: int = Field(default=5, alias="BACKGROUND_REVIEW_MIN_TOOL_CALLS")
    background_review_max_rounds: int = Field(default=8, alias="BACKGROUND_REVIEW_MAX_ROUNDS")

    # 记忆策展：总条数超过上限触发一次 LLM 去重/合并/淘汰
    memory_max_items: int = Field(default=200, alias="MEMORY_MAX_ITEMS")
    memory_curate_batch: int = Field(default=60, alias="MEMORY_CURATE_BATCH")

    # 写入安全门：是否启用（LLM 语义审查为主）
    write_guard_enabled: bool = Field(default=True, alias="WRITE_GUARD_ENABLED")

    # 向量召回：余弦距离上限（距离越小越相关），超过则视为不相关丢弃
    recall_max_distance: float = Field(default=0.6, alias="RECALL_MAX_DISTANCE")

    # MCP 工具调用超时（秒）：避免上游插件异常时调用长期挂起
    mcp_call_timeout_seconds: float = Field(default=45.0, alias="MCP_CALL_TIMEOUT_SECONDS")
    # MCP 单服连接超时（秒）：start() 并行连接时每服上限，避免一服拖死整批
    mcp_connect_timeout_seconds: float = Field(default=30.0, alias="MCP_CONNECT_TIMEOUT_SECONDS")
    # 被踢掉/离线 MCP 首次重连等待（秒），再发起连接
    mcp_reconnect_delay_seconds: float = Field(default=5.0, alias="MCP_RECONNECT_DELAY_SECONDS")
    # 定时扫描并重连未连接 MCP 的间隔（秒）；0 表示关闭
    mcp_reconnect_interval_seconds: float = Field(default=60.0, alias="MCP_RECONNECT_INTERVAL_SECONDS")

    # 工具循环护栏（单轮对话内重复失败 / 只读无进展检测）
    tool_guardrail_warnings_enabled: bool = Field(default=True, alias="TOOL_GUARDRAIL_WARNINGS_ENABLED")
    tool_guardrail_hard_stop_enabled: bool = Field(default=True, alias="TOOL_GUARDRAIL_HARD_STOP_ENABLED")
    tool_guardrail_exact_failure_warn_after: int = Field(default=2, alias="TOOL_GUARDRAIL_EXACT_FAILURE_WARN_AFTER")
    tool_guardrail_exact_failure_block_after: int = Field(default=5, alias="TOOL_GUARDRAIL_EXACT_FAILURE_BLOCK_AFTER")
    tool_guardrail_same_tool_failure_warn_after: int = Field(
        default=3, alias="TOOL_GUARDRAIL_SAME_TOOL_FAILURE_WARN_AFTER"
    )
    tool_guardrail_same_tool_failure_halt_after: int = Field(
        default=8, alias="TOOL_GUARDRAIL_SAME_TOOL_FAILURE_HALT_AFTER"
    )
    tool_guardrail_no_progress_warn_after: int = Field(default=2, alias="TOOL_GUARDRAIL_NO_PROGRESS_WARN_AFTER")
    tool_guardrail_no_progress_block_after: int = Field(default=5, alias="TOOL_GUARDRAIL_NO_PROGRESS_BLOCK_AFTER")

    # 流式 LLM：单 chunk 空闲超时（秒）与整段上限（0 表示不限制整段）
    stream_chunk_timeout_s: float = Field(default=90.0, alias="STREAM_CHUNK_TIMEOUT_S")
    stream_max_duration_s: float = Field(default=600.0, alias="STREAM_MAX_DURATION_S")


@lru_cache
def get_settings() -> Settings:
    return Settings()
