"""MCP server 配置：YAML 持久化在各工作区 agent.sqlite 同目录。

mcp.yaml 示例::

    servers:
      - name: notion
        transport: http
        url: https://mcp.notion.com/mcp
        auth: oauth   # 保存时按 registration_endpoint 自动探测

      - name: github
        transport: http
        url: https://api.githubcopilot.com/mcp/
        headers:
          Authorization: "Bearer ghp_xxx"

      - name: local
        transport: stdio
        command: [npx, "@scope/mcp"]
        env:
          API_KEY: xxx
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
    headers: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    auth: AuthMode = "none"

    def to_dict(self) -> dict:
        d = asdict(self)
        if not d.get("env"):
            d.pop("env", None)
        if not d.get("headers"):
            d.pop("headers", None)
        return d

    def to_public_dict(self) -> dict:
        d = self.to_dict()
        if d.get("headers"):
            d["headers"] = mask_sensitive_headers(d["headers"])
        return d


def mask_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    if not headers:
        return {}
    out: dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() == "authorization" and len(v) > 12:
            out[k] = f"{v[:8]}…"
        else:
            out[k] = v
    return out


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
    return "none"


def _str_dict(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict) or not raw:
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if key:
            out[key] = str(v)
    return out


def _normalize_server_item(item: dict) -> tuple[dict, bool]:
    changed = False
    normalized = dict(item)
    env_raw = normalized.get("env")
    headers_raw = normalized.get("headers")
    if isinstance(env_raw, dict) and not env_raw:
        normalized.pop("env", None)
        changed = True
    if isinstance(headers_raw, dict) and not headers_raw:
        normalized.pop("headers", None)
        changed = True
    return normalized, changed


def load_mcp_config(workspace_id: str | None = None) -> list[MCPServerConfig]:
    path = _config_path(workspace_id)
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = raw.get("servers") or []
    out: list[MCPServerConfig] = []
    stale_empty = False
    for item in servers:
        if not isinstance(item, dict):
            continue
        try:
            item, normalized = _normalize_server_item(item)
            stale_empty = stale_empty or normalized
            env_raw = item.get("env")
            headers_raw = item.get("headers")
            if isinstance(env_raw, dict) and not env_raw:
                stale_empty = True
            if isinstance(headers_raw, dict) and not headers_raw:
                stale_empty = True
            out.append(
                MCPServerConfig(
                    name=str(item["name"]),
                    transport=item.get("transport", "stdio"),
                    command=list(item.get("command", []) or []),
                    args=list(item.get("args", []) or []),
                    env=_str_dict(env_raw),
                    headers=_str_dict(headers_raw),
                    url=item.get("url"),
                    auth=_normalize_auth(item.get("transport", "stdio"), item.get("auth")),
                )
            )
        except KeyError:
            continue
    if stale_empty and out:
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
    if cfg.transport == "stdio":
        if cfg.auth != "none":
            raise ValueError("stdio transport does not support oauth auth")
        if cfg.headers:
            raise ValueError("stdio transport does not support headers")
    if cfg.transport == "http" and cfg.env:
        raise ValueError("http transport uses headers, not env")
    if cfg.transport == "http" and cfg.auth == "oauth" and cfg.headers:
        raise ValueError("oauth auth does not use headers")


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
