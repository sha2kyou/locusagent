"""LLM 客户端（OpenAI 兼容）。"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from ..config import get_settings


@lru_cache
def get_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.internal_token,
        max_retries=2,
        timeout=300.0,
    )
