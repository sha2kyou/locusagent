"""AgentPod 本地服务端口（避免与常见开发端口冲突）。"""

from __future__ import annotations

AGENTPOD_HOST = "127.0.0.1"
AGENTPOD_PORT = 21223


def agentpod_base_url() -> str:
    return f"http://{AGENTPOD_HOST}:{AGENTPOD_PORT}"


def agentpod_llm_internal_url() -> str:
    return f"{agentpod_base_url()}/internal/llm/v1"
