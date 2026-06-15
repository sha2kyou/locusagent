"""工作区 ID：ws_ + 20 位小写 hex。"""

from __future__ import annotations

import re
import secrets

WORKSPACE_ID_RE = re.compile(r"^ws_[a-f0-9]{20}$")


def generate_workspace_id() -> str:
    return f"ws_{secrets.token_hex(10)}"


def is_valid_workspace_id(value: str | None) -> bool:
    raw = (value or "").strip().lower()
    return bool(raw and WORKSPACE_ID_RE.fullmatch(raw))


def normalize_workspace_id(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not is_valid_workspace_id(raw):
        raise ValueError(f"invalid workspace id: {value!r}")
    return raw
