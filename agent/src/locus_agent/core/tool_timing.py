"""Tool 执行计时：started_at 落库与活跃 run 内存登记（供刷新恢复 UI 计时）。"""

from __future__ import annotations

import time
from typing import Any

_UI_TOOL_CALL_KEYS = frozenset({"started_at", "tool_kind"})


def tool_round_started_at() -> float:
    return time.time()


def annotate_tool_calls_started_at(
    tool_calls: Any,
    *,
    started_at: float | None = None,
) -> list[dict[str, Any]] | Any:
    """为 assistant tool_calls 附加 started_at（Unix 秒，浮点）。"""
    if not isinstance(tool_calls, list) or not tool_calls:
        return tool_calls
    stamp = float(started_at if started_at is not None else tool_round_started_at())
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            out.append(tc)
            continue
        row = dict(tc)
        if row.get("started_at") is None:
            row["started_at"] = stamp
        out.append(row)
    return out


def started_at_from_tool_call(tc: Any) -> float | None:
    if not isinstance(tc, dict):
        return None
    raw = tc.get("started_at")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def sanitize_tool_calls_for_llm(tool_calls: Any) -> list[dict[str, Any]]:
    """回放 LLM API 时去掉 UI 扩展字段。"""
    if not isinstance(tool_calls, list):
        return []
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        tc_id = str(tc.get("id") or "").strip()
        if not tc_id:
            continue
        out.append(
            {
                "id": tc_id,
                "type": str(tc.get("type") or "function"),
                "function": {
                    "name": str(fn.get("name") or ""),
                    "arguments": str(fn.get("arguments") or ""),
                },
            }
        )
    return out


_active_tool_starts: dict[str, dict[str, float]] = {}


def register_tool_start(session_id: str, tool_call_id: str, started_at: float) -> None:
    sid = str(session_id or "").strip()
    tcid = str(tool_call_id or "").strip()
    if not sid or not tcid:
        return
    stamp = float(started_at)
    if stamp <= 0:
        return
    bucket = _active_tool_starts.setdefault(sid, {})
    bucket[tcid] = stamp


def clear_tool_start(session_id: str, tool_call_id: str) -> None:
    sid = str(session_id or "").strip()
    tcid = str(tool_call_id or "").strip()
    if not sid or not tcid:
        return
    bucket = _active_tool_starts.get(sid)
    if not bucket:
        return
    bucket.pop(tcid, None)
    if not bucket:
        _active_tool_starts.pop(sid, None)


def clear_session_tool_starts(session_id: str) -> None:
    sid = str(session_id or "").strip()
    if sid:
        _active_tool_starts.pop(sid, None)


def list_active_tool_starts(session_id: str) -> list[dict[str, Any]]:
    sid = str(session_id or "").strip()
    if not sid:
        return []
    bucket = _active_tool_starts.get(sid) or {}
    return [
        {"tool_call_id": tcid, "started_at": stamp}
        for tcid, stamp in sorted(bucket.items(), key=lambda x: x[1])
    ]
