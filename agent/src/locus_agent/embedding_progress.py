"""当前工作区向量化进度汇总。"""

from __future__ import annotations

from typing import Any

from .db import conn_scope, run_in_thread
from .memory.queue import get_embedding_queue_stats
from .skills.embeddings import get_skill_reindex_pending
from .workspace import get_workspace_id

_TABLES: dict[str, str] = {
    "memory": "memory",
    "message": "messages",
    "artifact": "artifacts",
    "env_var": "env_vars",
    "skill": "skill_embeddings",
}


def _empty_counts() -> dict[str, int]:
    return {"pending": 0, "ready": 0, "failed": 0, "skipped": 0}


def _count_by_state(table: str) -> dict[str, int]:
    counts = _empty_counts()
    with conn_scope(load_vec=False) as c:
        rows = c.execute(
            f"SELECT embedding_state, COUNT(*) AS n FROM {table} GROUP BY embedding_state"
        ).fetchall()
    for row in rows:
        state = str(row["embedding_state"])
        if state in counts:
            counts[state] = int(row["n"])
    return counts


def _aggregate_counts(by_kind: dict[str, dict[str, int]]) -> dict[str, int]:
    totals = _empty_counts()
    for counts in by_kind.values():
        for key in totals:
            totals[key] += counts.get(key, 0)
    return totals


def _build_summary(totals: dict[str, int]) -> dict[str, Any]:
    ready = totals.get("ready", 0)
    pending = totals.get("pending", 0)
    failed = totals.get("failed", 0)
    skipped = totals.get("skipped", 0)
    indexable = ready + pending + failed
    remaining = pending + failed
    percent: float | None = None
    if indexable > 0:
        percent = round(ready / indexable * 100, 1)
    return {
        "ready": ready,
        "pending": pending,
        "failed": failed,
        "skipped": skipped,
        "remaining": remaining,
        "indexable": indexable,
        "percent": percent,
    }


def _collect_progress(*, workspace_id: str) -> dict[str, Any]:
    by_kind = {kind: _count_by_state(table) for kind, table in _TABLES.items()}
    totals = _aggregate_counts(by_kind)
    summary = _build_summary(totals)
    queue = get_embedding_queue_stats(workspace_id=workspace_id)
    skill_reindex = get_skill_reindex_pending()
    active = (
        summary["remaining"] > 0
        or queue["queued"] > 0
        or queue["retry_waiting"] > 0
        or skill_reindex["pending_skills"] > 0
        or skill_reindex["full_reindex"]
    )
    return {
        "workspace_id": workspace_id,
        "active": active,
        "summary": summary,
        "by_kind": by_kind,
        "queue": queue,
        "skill_reindex": skill_reindex,
    }


async def get_embedding_progress() -> dict[str, Any]:
    workspace_id = get_workspace_id()
    return await run_in_thread(_collect_progress, workspace_id=workspace_id)
