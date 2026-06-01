"""子进程环境：不继承 INTERNAL_TOKEN 等敏感变量。"""

from __future__ import annotations

import os

_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "PYTHONHOME", "TZ")


def safe_subprocess_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ and os.environ[k]}
