"""Locus Agent 本地服务端口（避免与常见开发端口冲突）。"""

from __future__ import annotations

LOCUSAGENT_HOST = "127.0.0.1"
LOCUSAGENT_PORT = 21223


def locusagent_base_url() -> str:
    return f"http://{LOCUSAGENT_HOST}:{LOCUSAGENT_PORT}"


def locusagent_llm_internal_url() -> str:
    return f"{locusagent_base_url()}/internal/llm/v1"
