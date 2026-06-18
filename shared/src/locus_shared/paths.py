"""~/.locusagent 路径约定。"""

from __future__ import annotations

import os
from pathlib import Path


def expand_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def locusagent_home() -> Path:
    override = os.environ.get("LOCUSAGENT_HOME", "").strip()
    if override:
        return expand_path(override)
    return Path.home() / ".locusagent"


def ensure_locusagent_home() -> Path:
    home = locusagent_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "attachments").mkdir(parents=True, exist_ok=True)
    (home / "workspaces").mkdir(parents=True, exist_ok=True)
    (home / "models").mkdir(parents=True, exist_ok=True)
    return home
