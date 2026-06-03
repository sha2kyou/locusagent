"""内置工具共用的参数解析。"""

from __future__ import annotations

from typing import Any


def pick_str(args: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = args.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if text:
            return text
    return ""


def pick_int(args: dict[str, Any], *keys: str) -> int:
    for key in keys:
        val = args.get(key)
        if val is None or val == "":
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            continue
    return 0


def pick_action(args: dict[str, Any], *, default: str = "") -> str:
    return str(args.get("action", default) or default).strip().lower()
