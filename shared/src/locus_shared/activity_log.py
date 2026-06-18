"""应用内操作日志：JSONL 持久化于 ~/.agentpod/activity.jsonl。"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import ensure_agentpod_home

_MAX_LINES = 3000
_TRIM_TO = 2000
_LOCK = threading.Lock()
_NEXT_ID = 0
_ID_LOADED = False

SENSITIVE_DETAIL_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "token",
        "secret",
        "value",
    }
)


def activity_log_path() -> Path:
    return ensure_agentpod_home() / "activity.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if not detail:
        return None
    out: dict[str, Any] = {}
    for key, value in detail.items():
        key_l = str(key).lower()
        if any(s in key_l for s in SENSITIVE_DETAIL_KEYS):
            out[key] = "[已隐藏]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = value[:20]
        else:
            out[key] = str(value)[:200]
    return out or None


def _load_next_id(path: Path) -> None:
    global _NEXT_ID, _ID_LOADED
    if _ID_LOADED:
        return
    _ID_LOADED = True
    if not path.is_file():
        _NEXT_ID = 0
        return
    last_id = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last_id = max(last_id, int(row.get("id") or 0))
    except OSError:
        last_id = 0
    _NEXT_ID = last_id


def _trim_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= _MAX_LINES:
        return
    kept = lines[-_TRIM_TO:]
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def record_activity(
    category: str,
    action: str,
    message: str,
    *,
    workspace_id: str | None = None,
    level: str = "info",
    detail: dict[str, Any] | None = None,
) -> int:
    """写入一条操作日志，返回自增 id。"""
    global _NEXT_ID
    cat = str(category or "system").strip() or "system"
    act = str(action or "event").strip() or "event"
    msg = str(message or "").strip()
    if not msg:
        msg = f"{cat}.{act}"
    lvl = str(level or "info").strip().lower() or "info"
    if lvl not in {"info", "warn", "error"}:
        lvl = "info"

    path = activity_log_path()
    with _LOCK:
        _load_next_id(path)
        _NEXT_ID += 1
        entry_id = _NEXT_ID
        row = {
            "id": entry_id,
            "ts": _now_iso(),
            "category": cat,
            "action": act,
            "message": msg,
            "workspace_id": workspace_id,
            "level": lvl,
            "detail": _sanitize_detail(detail),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        _trim_file(path)
    return entry_id


def list_activity_logs(*, limit: int = 200, after_id: int | None = None) -> list[dict[str, Any]]:
    """按时间倒序返回操作日志（最新在前）。"""
    lim = max(1, min(int(limit), 500))
    path = activity_log_path()
    if not path.is_file():
        return []

    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                rows.append(row)
    except OSError:
        return []

    if after_id is not None:
        rows = [r for r in rows if int(r.get("id") or 0) > after_id]

    rows.sort(key=lambda r: int(r.get("id") or 0), reverse=True)
    return rows[:lim]
