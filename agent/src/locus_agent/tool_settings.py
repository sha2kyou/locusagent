"""工具开关持久化：内置工具 / 技能 / MCP 服务启停。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .workspace import workspace_data_dir


@dataclass(slots=True)
class ToolSettings:
    builtin_tools: dict[str, bool] = field(default_factory=dict)
    skills: dict[str, bool] = field(default_factory=dict)
    mcp_servers: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "builtin_tools": dict(self.builtin_tools),
            "skills": dict(self.skills),
            "mcp_servers": dict(self.mcp_servers),
        }


def _settings_path() -> Path:
    return workspace_data_dir() / "tool_settings.yaml"


def load_tool_settings() -> ToolSettings:
    path = _settings_path()
    if not path.is_file():
        return ToolSettings()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ToolSettings(
        builtin_tools=_normalize(raw.get("builtin_tools")),
        skills=_normalize(raw.get("skills")),
        mcp_servers=_normalize(raw.get("mcp_servers")),
    )


def save_tool_settings(settings: ToolSettings) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(settings.to_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def set_builtin_tool_enabled(name: str, enabled: bool) -> ToolSettings:
    data = load_tool_settings()
    data.builtin_tools[name] = bool(enabled)
    save_tool_settings(data)
    return data


def set_skill_enabled(name: str, enabled: bool) -> ToolSettings:
    data = load_tool_settings()
    data.skills[name] = bool(enabled)
    save_tool_settings(data)
    if enabled:
        from .skills.embeddings import mark_skill_reindex

        mark_skill_reindex(name)
    else:
        from .skills.embeddings import delete_skill_embeddings

        delete_skill_embeddings(name)
    return data


def is_skill_enabled(name: str) -> bool:
    data = load_tool_settings()
    return data.skills.get(name, True)


def is_mcp_server_enabled(name: str) -> bool:
    data = load_tool_settings()
    return data.mcp_servers.get(name, True)


def _normalize(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, bool] = {}
    for k, v in value.items():
        key = str(k).strip()
        if not key:
            continue
        out[key] = bool(v)
    return out
