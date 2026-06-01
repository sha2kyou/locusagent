"""模型角色解析（对齐 Hermes auxiliary，空值回退主模型）。"""

from __future__ import annotations

from typing import Any, Literal

from ..config import get_settings

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


def resolve_model(role: ModelRole) -> str:
    settings = get_settings()
    main = settings.llm_model
    overrides = {
        "main": main,
        "vision": settings.auxiliary_vision_model,
        "web_extract": settings.auxiliary_web_extract_model,
        "compression": settings.auxiliary_compression_model,
        "title_generation": settings.auxiliary_title_generation_model,
        "approval": settings.auxiliary_approval_model,
        "curator": settings.auxiliary_curator_model,
        "skill_reflect": settings.auxiliary_skill_reflect_model,
        "memory_autostore": settings.auxiliary_memory_autostore_model,
    }
    chosen = (overrides.get(role) or "").strip()
    return chosen or main


def messages_include_images(messages: list[dict[str, Any]]) -> bool:
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return True
    return False
