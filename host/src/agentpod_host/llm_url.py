"""从 LLM_BASE_URL 解析路径前缀，供代理与容器 base 拼接。"""

from __future__ import annotations

from urllib.parse import urlparse


def llm_base_path_prefix(llm_base_url: str) -> str:
    return urlparse(llm_base_url).path.strip("/")


def host_llm_proxy_base_url(*, host_internal_base: str, llm_base_url: str) -> str:
    base = f"{host_internal_base.rstrip('/')}/internal/llm"
    prefix = llm_base_path_prefix(llm_base_url)
    if prefix:
        return f"{base}/{prefix}"
    return base


def upstream_url_for_proxy_path(*, llm_base_url: str, path: str) -> str:
    """代理 path 含 LLM_BASE_URL 的路径前缀时去掉前缀，再拼到 LLM_BASE_URL。"""
    prefix = llm_base_path_prefix(llm_base_url)
    rel = path.lstrip("/")
    if prefix:
        expected = f"{prefix}/"
        if not rel.startswith(expected):
            raise ValueError(f"path must start with {prefix}/")
        rel = rel[len(expected) :]
    return f"{llm_base_url.rstrip('/')}/{rel}"
