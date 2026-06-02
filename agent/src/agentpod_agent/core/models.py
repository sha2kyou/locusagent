"""模型角色解析：名称仅由 Host 配置，Agent 经 internal API 查询。"""

from __future__ import annotations

from typing import Any, Literal

from ..host_settings import get_resolved_model

ModelRole = Literal[
    "main",
    "vision",
    "web_extract",
    "compression",
    "title_generation",
    "approval",
    "curator",
    "skill_reflect",
    "memory_autostore",
]

# Hermes 有、AgentPod 当前无 LLM 调用
HERMES_ROLES_NOT_IMPLEMENTED = (
    "skills_hub",
    "mcp",
    "triage_specifier",
    "kanban_decomposer",
    "profile_describer",
)


async def resolve_model(role: ModelRole) -> str:
    return await get_resolved_model(role)


def messages_include_images(messages: list[dict[str, Any]]) -> bool:
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False
