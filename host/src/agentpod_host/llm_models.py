"""LLM 辅助模型角色（对齐 Hermes auxiliary 命名，空值回退主模型）。"""

from __future__ import annotations

from typing import Literal

from .config import Settings, get_settings

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

ROLE_ENV_KEYS: dict[ModelRole, str] = {
    "main": "LLM_MODEL",
    "vision": "AUXILIARY_VISION_MODEL",
    "web_extract": "AUXILIARY_WEB_EXTRACT_MODEL",
    "compression": "AUXILIARY_COMPRESSION_MODEL",
    "title_generation": "AUXILIARY_TITLE_GENERATION_MODEL",
    "approval": "AUXILIARY_APPROVAL_MODEL",
    "curator": "AUXILIARY_CURATOR_MODEL",
    "skill_reflect": "AUXILIARY_SKILL_REFLECT_MODEL",
    "memory_autostore": "AUXILIARY_MEMORY_AUTOSTORE_MODEL",
}

# Hermes 有、AgentPod 当前无对应 LLM 调用
HERMES_ROLES_NOT_IMPLEMENTED = (
    "skills_hub",
    "mcp",
    "triage_specifier",
    "kanban_decomposer",
    "profile_describer",
)

_AUXILIARY_FIELDS: list[tuple[str, str]] = [
    ("AUXILIARY_VISION_MODEL", "auxiliary_vision_model"),
    ("AUXILIARY_WEB_EXTRACT_MODEL", "auxiliary_web_extract_model"),
    ("AUXILIARY_COMPRESSION_MODEL", "auxiliary_compression_model"),
    ("AUXILIARY_TITLE_GENERATION_MODEL", "auxiliary_title_generation_model"),
    ("AUXILIARY_APPROVAL_MODEL", "auxiliary_approval_model"),
    ("AUXILIARY_CURATOR_MODEL", "auxiliary_curator_model"),
    ("AUXILIARY_SKILL_REFLECT_MODEL", "auxiliary_skill_reflect_model"),
    ("AUXILIARY_MEMORY_AUTOSTORE_MODEL", "auxiliary_memory_autostore_model"),
]


def resolve_model(role: ModelRole, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    main = s.llm_model
    if role == "main":
        return main
    override = getattr(s, _role_to_field(role), "")
    chosen = (override or "").strip()
    return chosen or main


def _role_to_field(role: ModelRole) -> str:
    if role == "main":
        raise ValueError("main has no auxiliary field")
    for _env, field in _AUXILIARY_FIELDS:
        if ROLE_ENV_KEYS[role] == _env:
            return field
    raise KeyError(role)


def auxiliary_env_for_agent(settings: Settings | None = None) -> dict[str, str]:
    """注入 Agent 容器的模型名（非密钥）。"""
    s = settings or get_settings()
    env: dict[str, str] = {"LLM_MODEL": s.llm_model}
    for env_key, field in _AUXILIARY_FIELDS:
        value = (getattr(s, field) or "").strip()
        if value:
            env[env_key] = value
    return env
