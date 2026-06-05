"""Session 级 background review nudge 计数器（对齐 Hermes _turns_since_memory / _iters_since_skill）。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import get_settings
from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from .persistence import count_user_turns

log = get_logger("session_review_state")


@dataclass(slots=True)
class ReviewNudgeState:
    turns_since_memory: int = 0
    iters_since_skill: int = 0
    pending_memory_review: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "turns_since_memory": self.turns_since_memory,
                "iters_since_skill": self.iters_since_skill,
                "pending_memory_review": self.pending_memory_review,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str | None) -> ReviewNudgeState:
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            turns_since_memory=max(0, int(data.get("turns_since_memory") or 0)),
            iters_since_skill=max(0, int(data.get("iters_since_skill") or 0)),
            pending_memory_review=bool(data.get("pending_memory_review", False)),
        )


async def _load_state(session_id: str) -> ReviewNudgeState:
    sid = str(session_id or "").strip()
    if not sid:
        return ReviewNudgeState()

    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT review_state FROM sessions WHERE id = ?",
                (sid,),
            ).fetchone()
            if row is None:
                return None
            value = row["review_state"]
            return str(value) if value else None

    raw = await run_in_thread(_do)
    return ReviewNudgeState.from_json(raw)


async def _save_state(session_id: str, state: ReviewNudgeState) -> None:
    sid = str(session_id or "").strip()
    if not sid:
        return

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE sessions SET review_state = ? WHERE id = ?",
                (state.to_json(), sid),
            )

    await run_in_thread(_do)


async def flush_disabled_review_state(session_id: str) -> None:
    """Review 关闭时清除 pending 状态，避免 re-enable 后误触发。"""
    state = await _load_state(session_id)
    if not state.pending_memory_review:
        return
    state.pending_memory_review = False
    await _save_state(session_id, state)


async def begin_user_turn(session_id: str) -> None:
    """用户轮次开始：递增 memory nudge 计数，必要时置 pending_memory_review（对齐 Hermes turn 开头）。"""
    settings = get_settings()
    if not settings.background_review_enabled:
        return
    interval = settings.background_review_memory_nudge_turns
    if interval <= 0:
        return

    state = await _load_state(session_id)
    if state.turns_since_memory == 0 and state.iters_since_skill == 0 and not state.pending_memory_review:
        prior_turns = max(0, await count_user_turns(session_id) - 1)
        if prior_turns > 0:
            state.turns_since_memory = prior_turns % interval

    state.turns_since_memory += 1
    if state.turns_since_memory >= interval:
        state.pending_memory_review = True
        state.turns_since_memory = 0

    await _save_state(session_id, state)
    if state.pending_memory_review:
        log.info(
            "review_memory_nudge_pending",
            session_id=session_id,
            interval=interval,
        )


async def reset_memory_nudge(session_id: str) -> None:
    """前台 memory 工具调用后重置 memory nudge 计数（对齐 Hermes tool_executor）。"""
    state = await _load_state(session_id)
    state.turns_since_memory = 0
    await _save_state(session_id, state)


async def reset_skill_nudge(session_id: str) -> None:
    """前台 skill_manage 调用后重置 skill nudge 计数。"""
    state = await _load_state(session_id)
    state.iters_since_skill = 0
    await _save_state(session_id, state)


async def assess_turn_end_review_triggers(
    session_id: str,
    *,
    loop_rounds: int,
) -> tuple[bool, bool]:
    """轮次结束：读取 pending memory review，按 loop_rounds 评估 skill review。"""
    settings = get_settings()
    state = await _load_state(session_id)

    review_memory = state.pending_memory_review
    state.pending_memory_review = False

    skill_interval = settings.background_review_skill_nudge_loop_rounds
    review_skills = False
    if skill_interval > 0 and loop_rounds > 0:
        state.iters_since_skill += loop_rounds
        if state.iters_since_skill >= skill_interval:
            review_skills = True
            state.iters_since_skill = 0
            log.info(
                "review_skill_nudge_triggered",
                session_id=session_id,
                loop_rounds=loop_rounds,
                interval=skill_interval,
            )

    await _save_state(session_id, state)
    return review_memory, review_skills
