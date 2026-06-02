"""MCP server 配置：YAML 持久化在各工作区 agent.sqlite 同目录。

mcp.yaml 示例（HTTP + OAuth，如 Notion）::

    servers:
      - name: notion
        transport: http
        url: https://mcp.notion.com/mcp
        auth: oauth   # 未写 auth 的 http 默认为直连 none

在 MCP 页完成 Host OAuth 后 Agent 会经 internal 重连该服。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from ..workspace import get_workspace_id, normalize_workspace_id, workspace_data_dir

Transport = Literal["stdio", "http"]
AuthMode = Literal["none", "oauth"]


@dataclass(slots=True)
class MCPServerConfig:
    name: str
    transport: Transport
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    auth: AuthMode = "none"

    def to_dict(self) -> dict:
        d = asdict(self)
        if not d.get("env"):
            d.pop("env", None)
        return d


def _resolve_workspace_id(workspace_id: str | None) -> str:
    if workspace_id is not None:
        return normalize_workspace_id(workspace_id)
    return get_workspace_id()


def _config_path(workspace_id: str | None = None) -> Path:
    return workspace_data_dir(_resolve_workspace_id(workspace_id)) / "mcp.yaml"


def _normalize_auth(transport: str, auth: str | None) -> AuthMode:
    if transport != "http":
        return "none"
    if auth in ("none", "oauth"):
        return auth
    # 未写 auth 时保持直连；需 OAuth 时在 mcp.yaml 显式写 auth: oauth
    return "none"


def load_mcp_config(workspace_id: str | None = None) -> list[MCPServerConfig]:
    path = _config_path(workspace_id)
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = raw.get("servers") or []
    out: list[MCPServerConfig] = []
    stale_empty_env = False
    for item in servers:
        if not isinstance(item, dict):
            continue
        try:
            env_raw = item.get("env")
            if isinstance(env_raw, dict) and not env_raw:
                stale_empty_env = True
            env = dict(env_raw) if isinstance(env_raw, dict) and env_raw else {}
            out.append(
                MCPServerConfig(
                    name=str(item["name"]),
                    transport=item.get("transport", "stdio"),
                    command=list(item.get("command", []) or []),
                    args=list(item.get("args", []) or []),
                    env=env,
                    url=item.get("url"),
                    auth=_normalize_auth(item.get("transport", "stdio"), item.get("auth")),
                )
            )
        except KeyError:
            continue
    if stale_empty_env and out:
        _save_all(out, workspace_id=workspace_id)
    return out


def _save_all(items: list[MCPServerConfig], *, workspace_id: str | None = None) -> None:
    path = _config_path(workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"servers": [it.to_dict() for it in items]}
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def list_mcp_servers(workspace_id: str | None = None) -> list[MCPServerConfig]:
    return load_mcp_config(workspace_id)


def get_mcp_server(name: str, workspace_id: str | None = None) -> MCPServerConfig | None:
    for item in load_mcp_config(workspace_id):
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
    if cfg.transport == "stdio" and cfg.auth != "none":
        raise ValueError("stdio transport does not support oauth auth")


def add_mcp_server(cfg: MCPServerConfig, workspace_id: str | None = None) -> MCPServerConfig:
    _validate(cfg)
    items = load_mcp_config(workspace_id)
    if any(it.name == cfg.name for it in items):
        raise FileExistsError(f"mcp server already exists: {cfg.name}")
    items.append(cfg)
    _save_all(items, workspace_id=workspace_id)
    return cfg


def update_mcp_server(
    name: str,
    cfg: MCPServerConfig,
    workspace_id: str | None = None,
) -> MCPServerConfig:
    _validate(cfg)
    items = load_mcp_config(workspace_id)
    idx = next((i for i, it in enumerate(items) if it.name == name), -1)
    if idx < 0:
        raise FileNotFoundError(f"mcp server not found: {name}")
    if cfg.name != name and any(it.name == cfg.name for it in items):
        raise FileExistsError(f"mcp server already exists: {cfg.name}")
    items[idx] = cfg
    _save_all(items, workspace_id=workspace_id)
    return cfg


def remove_mcp_server(name: str, workspace_id: str | None = None) -> bool:
    items = load_mcp_config(workspace_id)
    new_items = [it for it in items if it.name != name]
    if len(new_items) == len(items):
        return False
    _save_all(new_items, workspace_id=workspace_id)
    return True
