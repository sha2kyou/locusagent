"""session review nudge 计数器测试。"""

from __future__ import annotations

import pytest

from agentpod_agent.core.background_review import assess_background_review_triggers
from agentpod_agent.core.session_review_state import (
    ReviewNudgeState,
    assess_turn_end_review_triggers,
    begin_user_turn,
    flush_disabled_review_state,
)


@pytest.mark.asyncio
async def test_assess_turn_end_skill_nudge(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentpod_agent import config as config_mod

    settings = config_mod.get_settings()
    monkeypatch.setattr(settings, "background_review_enabled", True)
    monkeypatch.setattr(settings, "background_review_skill_nudge_loop_rounds", 10)

    state = ReviewNudgeState(iters_since_skill=6, pending_memory_review=True)

    async def _load(_session_id: str) -> ReviewNudgeState:
        return state

    async def _save(_session_id: str, new_state: ReviewNudgeState) -> None:
        state.turns_since_memory = new_state.turns_since_memory
        state.iters_since_skill = new_state.iters_since_skill
        state.pending_memory_review = new_state.pending_memory_review

    monkeypatch.setattr(
        "agentpod_agent.core.session_review_state._load_state",
        _load,
    )
    monkeypatch.setattr(
        "agentpod_agent.core.session_review_state._save_state",
        _save,
    )

    review_memory, review_skills = await assess_turn_end_review_triggers("sess_test", loop_rounds=3)
    assert review_memory is True
    assert review_skills is False
    assert state.pending_memory_review is False
    assert state.iters_since_skill == 9

    review_memory, review_skills = await assess_turn_end_review_triggers("sess_test", loop_rounds=2)
    assert review_memory is False
    assert review_skills is True
    assert state.iters_since_skill == 0


@pytest.mark.asyncio
async def test_begin_user_turn_skips_when_review_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentpod_agent import config as config_mod

    settings = config_mod.get_settings()
    monkeypatch.setattr(settings, "background_review_enabled", False)
    monkeypatch.setattr(settings, "background_review_memory_nudge_turns", 10)

    called = {"load": False}

    async def _load(_session_id: str) -> ReviewNudgeState:
        called["load"] = True
        return ReviewNudgeState()

    monkeypatch.setattr("agentpod_agent.core.session_review_state._load_state", _load)
    await begin_user_turn("sess_disabled")
    assert called["load"] is False


@pytest.mark.asyncio
async def test_assess_background_review_disabled_clears_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentpod_agent import config as config_mod

    settings = config_mod.get_settings()
    monkeypatch.setattr(settings, "background_review_enabled", False)

    state = ReviewNudgeState(pending_memory_review=True, iters_since_skill=4)

    async def _load(_session_id: str) -> ReviewNudgeState:
        return state

    async def _save(_session_id: str, new_state: ReviewNudgeState) -> None:
        state.pending_memory_review = new_state.pending_memory_review

    monkeypatch.setattr("agentpod_agent.core.session_review_state._load_state", _load)
    monkeypatch.setattr("agentpod_agent.core.session_review_state._save_state", _save)

    review_memory, review_skills = await assess_background_review_triggers(
        session_id="sess_disabled",
        loop_rounds=3,
    )
    assert review_memory is False
    assert review_skills is False
    assert state.pending_memory_review is False
    assert state.iters_since_skill == 4


@pytest.mark.asyncio
async def test_flush_disabled_review_state_noop_without_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    state = ReviewNudgeState()

    async def _load(_session_id: str) -> ReviewNudgeState:
        return state

    saved = {"count": 0}

    async def _save(_session_id: str, _new_state: ReviewNudgeState) -> None:
        saved["count"] += 1

    monkeypatch.setattr("agentpod_agent.core.session_review_state._load_state", _load)
    monkeypatch.setattr("agentpod_agent.core.session_review_state._save_state", _save)

    await flush_disabled_review_state("sess_disabled")
    assert saved["count"] == 0
