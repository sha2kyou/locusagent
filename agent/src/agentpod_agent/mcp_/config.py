"""MCP server 配置：YAML 持久化在 /data/mcp.yaml。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from ..workspace import workspace_data_dir

Transport = Literal["stdio", "http"]


@dataclass(slots=True)
class MCPServerConfig:
    name: str
    transport: Transport
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _config_path() -> Path:
    return workspace_data_dir() / "mcp.yaml"


def load_mcp_config() -> list[MCPServerConfig]:
    path = _config_path()
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = raw.get("servers") or []
    out: list[MCPServerConfig] = []
    for item in servers:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                MCPServerConfig(
                    name=str(item["name"]),
                    transport=item.get("transport", "stdio"),
                    command=list(item.get("command", []) or []),
                    args=list(item.get("args", []) or []),
                    env=dict(item.get("env", {}) or {}),
                    url=item.get("url"),
                )
            )
        except KeyError:
            continue
    return out


def _save_all(items: list[MCPServerConfig]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"servers": [it.to_dict() for it in items]}
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def list_mcp_servers() -> list[MCPServerConfig]:
    return load_mcp_config()


def get_mcp_server(name: str) -> MCPServerConfig | None:
    for item in load_mcp_config():
        if item.name == name:
            return item
    return None


def _validate(cfg: MCPServerConfig) -> None:
    if not cfg.name:
        raise ValueError("name is required")
    if cfg.transport not in ("stdio", "http"):
        raise ValueError("transport must be stdio or http")
    if cfg.transport == "stdio" and not cfg.command:
        raise ValueError("stdio transport requires command")
    if cfg.transport == "http" and not cfg.url:
        raise ValueError("http transport requires url")


def add_mcp_server(cfg: MCPServerConfig) -> MCPServerConfig:
    _validate(cfg)
    items = load_mcp_config()
    if any(it.name == cfg.name for it in items):
        raise FileExistsError(f"mcp server already exists: {cfg.name}")
    items.append(cfg)
    _save_all(items)
    return cfg


def update_mcp_server(name: str, cfg: MCPServerConfig) -> MCPServerConfig:
    _validate(cfg)
    items = load_mcp_config()
    idx = next((i for i, it in enumerate(items) if it.name == name), -1)
    if idx < 0:
        raise FileNotFoundError(f"mcp server not found: {name}")
    if cfg.name != name and any(it.name == cfg.name for it in items):
        raise FileExistsError(f"mcp server already exists: {cfg.name}")
    items[idx] = cfg
    _save_all(items)
    return cfg


def remove_mcp_server(name: str) -> bool:
    items = load_mcp_config()
    new_items = [it for it in items if it.name != name]
    if len(new_items) == len(items):
        return False
    _save_all(new_items)
    return True
