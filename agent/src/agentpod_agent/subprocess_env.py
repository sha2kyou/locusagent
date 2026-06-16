"""子进程环境：不继承 INTERNAL_TOKEN 等敏感变量。"""

from __future__ import annotations

import os
from typing import Any

_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "PYTHONHOME", "TZ")
_RESERVED_ENV_PREFIXES = ("AGENTPOD_",)
_RESERVED_ENV_NAMES = frozenset(
    {
        "INTERNAL_TOKEN",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        *_SAFE_ENV_KEYS,
    }
)


def is_reserved_env_name(name: str) -> bool:
    n = str(name or "").strip()
    if not n:
        return False
    upper = n.upper()
    if upper in _RESERVED_ENV_NAMES:
        return True
    return any(upper.startswith(prefix) for prefix in _RESERVED_ENV_PREFIXES)


def safe_subprocess_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ and os.environ[k]}


def merge_subprocess_env(*, workspace_vars: dict[str, str] | None = None) -> dict[str, str]:
    env = safe_subprocess_env()
    if not workspace_vars:
        return env
    for key, value in workspace_vars.items():
        if is_reserved_env_name(key):
            continue
        env[key] = value
    return env


def normalize_env_names(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
