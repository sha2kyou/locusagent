"""LLM 客户端（OpenAI 兼容）。"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from ..config import get_settings


@lru_cache
def get_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    # api_key 使用 per-user INTERNAL_TOKEN；Host LLM 代理校验后注入平台 Key。
    headers: dict[str, str] = {}
    if settings.user_id:
        headers["X-User-Id"] = settings.user_id
    return AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.internal_token,
        default_headers=headers or None,
        max_retries=2,
        timeout=120.0,
    )
