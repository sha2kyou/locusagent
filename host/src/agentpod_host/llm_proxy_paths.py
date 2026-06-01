"""LLM 代理允许转发的上游路径（OpenAI 兼容子集）。"""

from __future__ import annotations

import re

from .config import get_settings
from .llm_url import llm_base_path_prefix


def _allowed_patterns(path_prefix: str) -> tuple[re.Pattern[str], ...]:
    if path_prefix:
        v = re.escape(path_prefix)
        return (
            re.compile(rf"^{v}/chat/completions$"),
            re.compile(rf"^{v}/completions$"),
            re.compile(rf"^{v}/models$"),
            re.compile(rf"^{v}/models/[^/]+$"),
            re.compile(rf"^{v}/embeddings$"),
        )
    return (
        re.compile(r"^chat/completions$"),
        re.compile(r"^completions$"),
        re.compile(r"^models$"),
        re.compile(r"^models/[^/]+$"),
        re.compile(r"^embeddings$"),
    )


def assert_llm_proxy_path_allowed(path: str) -> None:
    prefix = llm_base_path_prefix(get_settings().llm_base_url)
    normalized = path.strip().lstrip("/")
    if not normalized or ".." in normalized or normalized.startswith("/"):
        raise ValueError("invalid path")
    allowed = _allowed_patterns(prefix)
    if not any(p.match(normalized) for p in allowed):
        raise ValueError(f"path not allowed: {normalized}")
