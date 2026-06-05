"""LLM 辅助模型角色（空值回退主模型）。"""

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
}

_AUXILIARY_FIELDS: list[tuple[str, str]] = [
    ("AUXILIARY_VISION_MODEL", "auxiliary_vision_model"),
    ("AUXILIARY_WEB_EXTRACT_MODEL", "auxiliary_web_extract_model"),
    ("AUXILIARY_COMPRESSION_MODEL", "auxiliary_compression_model"),
    ("AUXILIARY_TITLE_GENERATION_MODEL", "auxiliary_title_generation_model"),
    ("AUXILIARY_APPROVAL_MODEL", "auxiliary_approval_model"),
    ("AUXILIARY_CURATOR_MODEL", "auxiliary_curator_model"),
    ("AUXILIARY_SKILL_REFLECT_MODEL", "auxiliary_skill_reflect_model"),
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

