"""会话任务计划持久化（SQLite）。"""

from __future__ import annotations

import json
import secrets
from typing import Any, Literal

from ..db import conn_scope, run_in_thread

STEP_STATUSES = frozenset({"pending", "in_progress", "done", "skipped", "interrupted"})
_AGENT_STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress", "skipped", "done"}),
    "in_progress": frozenset({"done", "skipped", "pending"}),
    "done": frozenset({"done"}),
    "skipped": frozenset({"skipped"}),
    "interrupted": frozenset(),
}

INTERRUPT_NOTE_RESTART = "执行中断（服务重启）"
INTERRUPT_NOTE_NEW_SESSION = "执行中断（已开新对话）"
INTERRUPT_NOTE_NEW_TURN = "执行中断（新话题）"

InterruptScope = Literal["in_progress", "active"]


_AGENT_STEP_STATUSES = frozenset({"pending", "in_progress", "done", "skipped"})
_MAX_STEPS = 20


def _validate_step_transition(current: str, next_status: str) -> None:
    allowed = _AGENT_STEP_TRANSITIONS.get(current, frozenset())
    if next_status not in allowed:
        if current == "interrupted":
            raise ValueError("step is interrupted and cannot be updated")
        raise ValueError(
            f"invalid status transition: {current} -> {next_status}"
        )


def _new_plan_id() -> str:
    return f"tp_{secrets.token_hex(6)}"


def _normalize_steps(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("steps must be an array")
    if len(raw) < 2:
        raise ValueError("steps must contain at least 2 items")
    if len(raw) > _MAX_STEPS:
        raise ValueError(f"steps must contain at most {_MAX_STEPS} items")

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each step must be an object")
        step_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not step_id:
            raise ValueError("each step requires a non-empty id")
        if step_id in seen:
            raise ValueError(f"duplicate step id: {step_id}")
        if not title:
            raise ValueError(f"step {step_id} requires a non-empty title")
        seen.add(step_id)
        detail = str(item.get("detail") or "").strip()
        step: dict[str, Any] = {
            "id": step_id,
            "title": title,
            "status": "pending",
        }
        if detail:
            step["detail"] = detail
        out.append(step)
    return out


def _row_to_plan(row: Any) -> dict[str, Any]:
    steps = json.loads(str(row["steps_json"] or "[]"))
    active = next((s["id"] for s in steps if s.get("status") == "in_progress"), None)
    plan: dict[str, Any] = {
        "plan_id": str(row["plan_id"]),
        "title": str(row["title"]),
        "steps": steps,
    }
    if active:
        plan["active_step_id"] = active
    return plan


def _target_statuses(scope: InterruptScope) -> frozenset[str]:
    if scope == "in_progress":
        return frozenset({"in_progress"})
    return frozenset({"pending", "in_progress"})


def _interrupt_steps(
    steps: list[dict[str, Any]],
    *,
    scope: InterruptScope,
    note: str,
) -> tuple[list[dict[str, Any]], int]:
    targets = _target_statuses(scope)
    interrupted = 0
    out: list[dict[str, Any]] = []
    for step in steps:
        row = dict(step)
        if row.get("status") in targets:
            row["status"] = "interrupted"
            row["note"] = note
            interrupted += 1
        out.append(row)
    return out, interrupted


def _persist_steps(c: Any, session_id: str, steps: list[dict[str, Any]]) -> None:
    c.execute(
        """
        UPDATE session_todos
        SET steps_json=?, updated_at=datetime('now')
        WHERE session_id=?
        """,
        (json.dumps(steps, ensure_ascii=False), session_id),
    )


def plan_to_json(plan: dict[str, Any] | None) -> str:
    if not plan:
        return json.dumps({"plan": None}, ensure_ascii=False)
    return json.dumps(plan, ensure_ascii=False)


async def get_plan(session_id: str) -> dict[str, Any] | None:
    sid = str(session_id or "").strip()
    if not sid:
        return None

    def _do() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT plan_id, title, steps_json FROM session_todos WHERE session_id=?",
                (sid,),
            ).fetchone()
            if not row:
                return None
            return _row_to_plan(row)

    return await run_in_thread(_do)


async def create_plan(session_id: str, *, title: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    task_title = str(title or "").strip()
    if not task_title:
        raise ValueError("title is required")
    normalized = _normalize_steps(steps)
    plan_id = _new_plan_id()
    payload = json.dumps(normalized, ensure_ascii=False)

    def _do() -> dict[str, Any]:
        with conn_scope(load_vec=False) as c:
            c.execute(
                """
                INSERT INTO session_todos (session_id, plan_id, title, steps_json, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    plan_id=excluded.plan_id,
                    title=excluded.title,
                    steps_json=excluded.steps_json,
                    updated_at=datetime('now')
                """,
                (sid, plan_id, task_title, payload),
            )
            row = c.execute(
                "SELECT plan_id, title, steps_json FROM session_todos WHERE session_id=?",
                (sid,),
            ).fetchone()
            return _row_to_plan(row)

    return await run_in_thread(_do)


async def confirm_step(
    session_id: str,
    *,
    step_id: str,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    target_id = str(step_id or "").strip()
    if not target_id:
        raise ValueError("step_id is required")
    next_status = str(status or "").strip().lower()
    if next_status not in _AGENT_STEP_STATUSES:
        raise ValueError("status must be one of: pending, in_progress, done, skipped")
    note_text = str(note or "").strip()

    def _do() -> dict[str, Any]:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT plan_id, title, steps_json FROM session_todos WHERE session_id=?",
                (sid,),
            ).fetchone()
            if not row:
                raise ValueError("no active todo plan; call todo(action=create) first")
            steps = json.loads(str(row["steps_json"] or "[]"))
            idx = next((i for i, s in enumerate(steps) if str(s.get("id")) == target_id), -1)
            if idx < 0:
                raise ValueError(f"step not found: {target_id}")

            if next_status == "in_progress":
                for step in steps:
                    if str(step.get("id")) != target_id and step.get("status") == "in_progress":
                        raise ValueError(
                            f"step {step.get('id')} is still in_progress; mark it done before starting another"
                        )

            step = dict(steps[idx])
            current_status = str(step.get("status") or "pending").strip().lower()
            _validate_step_transition(current_status, next_status)
            step["status"] = next_status
            if note_text:
                step["note"] = note_text
            elif next_status != "done" and "note" in step and next_status == "in_progress":
                step.pop("note", None)
            steps[idx] = step

            _persist_steps(c, sid, steps)
            return _row_to_plan(
                {
                    "plan_id": row["plan_id"],
                    "title": row["title"],
                    "steps_json": json.dumps(steps, ensure_ascii=False),
                }
            )

    return await run_in_thread(_do)


async def interrupt_in_progress_on_startup() -> dict[str, int]:
    """服务重启后，将所有进行中的步骤标为 interrupted。"""

    def _do() -> dict[str, int]:
        plans_updated = 0
        steps_interrupted = 0
        with conn_scope(load_vec=False) as c:
            rows = c.execute("SELECT session_id, steps_json FROM session_todos").fetchall()
            for row in rows:
                steps = json.loads(str(row["steps_json"] or "[]"))
                updated, count = _interrupt_steps(
                    steps,
                    scope="in_progress",
                    note=INTERRUPT_NOTE_RESTART,
                )
                if count <= 0:
                    continue
                steps_interrupted += count
                _persist_steps(c, str(row["session_id"]), updated)
                plans_updated += 1
        return {"plans_updated": plans_updated, "steps_interrupted": steps_interrupted}

    return await run_in_thread(_do)


async def interrupt_other_session_todos(exclude_session_id: str) -> dict[str, int]:
    """新开对话时，将其他会话未完成的步骤标为 interrupted。"""

    exclude = str(exclude_session_id or "").strip()

    def _do() -> dict[str, int]:
        plans_updated = 0
        steps_interrupted = 0
        with conn_scope(load_vec=False) as c:
            rows = c.execute("SELECT session_id, steps_json FROM session_todos").fetchall()
            for row in rows:
                sid = str(row["session_id"])
                if sid == exclude:
                    continue
                steps = json.loads(str(row["steps_json"] or "[]"))
                updated, count = _interrupt_steps(
                    steps,
                    scope="active",
                    note=INTERRUPT_NOTE_NEW_SESSION,
                )
                if count <= 0:
                    continue
                steps_interrupted += count
                _persist_steps(c, sid, updated)
                plans_updated += 1
        return {"plans_updated": plans_updated, "steps_interrupted": steps_interrupted}

    return await run_in_thread(_do)


async def interrupt_current_session_todos(
    session_id: str,
    *,
    note: str = INTERRUPT_NOTE_NEW_TURN,
) -> dict[str, int]:
    """同会话新 user 消息或重试时，将未完成步骤标为 interrupted。"""

    sid = str(session_id or "").strip()
    if not sid:
        return {"plans_updated": 0, "steps_interrupted": 0}

    def _do() -> dict[str, int]:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT session_id, steps_json FROM session_todos WHERE session_id=?",
                (sid,),
            ).fetchone()
            if not row:
                return {"plans_updated": 0, "steps_interrupted": 0}
            steps = json.loads(str(row["steps_json"] or "[]"))
            updated, count = _interrupt_steps(
                steps,
                scope="active",
                note=note,
            )
            if count <= 0:
                return {"plans_updated": 0, "steps_interrupted": 0}
            _persist_steps(c, sid, updated)
            return {"plans_updated": 1, "steps_interrupted": count}

    return await run_in_thread(_do)


async def delete_session_todos(session_id: str) -> None:
    sid = str(session_id or "").strip()
    if not sid:
        return

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute("DELETE FROM session_todos WHERE session_id=?", (sid,))

    await run_in_thread(_do)
