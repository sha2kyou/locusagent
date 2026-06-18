"""Skill 分块与向量路由测试。"""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, patch

import pytest

from locus_agent.db import init_db
from locus_agent.skills import Skill, create_skill, delete_skill
from locus_agent.skills.chunking import chunk_skill
from locus_agent.skills.embeddings import (
    _cosine_distance,
    flush_pending_skill_reindexes,
    mark_skill_reindex,
    match_skills,
    reindex_all_skills,
    reindex_skill,
    sync_skill_index,
)
from locus_agent.skills.router import build_skill_route_message
from locus_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db() -> None:
    set_workspace_id(WS_TEST)
    init_db()


def _vec(*values: float) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def test_chunk_skill_splits_sections() -> None:
    skill = Skill(
        name="demo",
        description="Demo skill for testing",
        body="# Title\n\nIntro.\n\n## When to use\n\nUse for tests.\n\n## Workflow\n\nStep one.",
        source="private",
    )
    chunks = chunk_skill(skill)
    ids = [chunk_id for chunk_id, _ in chunks]
    assert "meta" in ids
    assert any(item.startswith("section:") for item in ids)
    assert any("When to use" in text for _, text in chunks)


def test_cosine_distance_identical_vectors() -> None:
    assert _cosine_distance([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_match_skills_returns_best_skill() -> None:
    delete_skill("alpha")
    delete_skill("beta")
    create_skill(
        Skill(
            name="alpha",
            description="humanize and polish writing",
            body="## When to use\n\nPolish drafts.",
            source="private",
        )
    )
    create_skill(
        Skill(
            name="beta",
            description="spreadsheet and excel analysis",
            body="## When to use\n\nAnalyze tables.",
            source="private",
        )
    )
    sync_skill_index(
        Skill(
            name="alpha",
            description="humanize and polish writing",
            body="## When to use\n\nPolish drafts.",
            source="private",
        )
    )
    sync_skill_index(
        Skill(
            name="beta",
            description="spreadsheet and excel analysis",
            body="## When to use\n\nAnalyze tables.",
            source="private",
        )
    )

    query_vec = [1.0, 0.0, 0.0]
    alpha_vec = [0.95, 0.05, 0.0]
    beta_vec = [0.0, 1.0, 0.0]

    async def _fake_embed(text: str) -> bytes:
        if "polish" in text.lower() or "humanize" in text.lower():
            return _vec(*alpha_vec)
        if "excel" in text.lower() or "spreadsheet" in text.lower():
            return _vec(*beta_vec)
        return _vec(*query_vec)

    with patch("locus_agent.skills.embeddings.embed_text", new=AsyncMock(side_effect=_fake_embed)):
        await reindex_skill("alpha")
        await reindex_skill("beta")
        matches = await match_skills("help me polish this draft", top_k=1)

    assert matches
    assert matches[0].skill_name == "alpha"


@pytest.mark.asyncio
async def test_mark_skill_reindex_from_sync_context_is_flushed() -> None:
    delete_skill("alpha")
    delete_skill("beta")
    create_skill(
        Skill(
            name="alpha",
            description="humanize and polish writing",
            body="## When to use\n\nPolish drafts.",
            source="private",
        )
    )

    target = _vec(1.0, 0.0, 0.0)
    far = _vec(0.0, 1.0, 0.0)

    async def _fake_embed(text: str) -> bytes:
        lowered = text.lower()
        if "polish this paragraph" in lowered:
            return target
        if lowered.startswith("alpha:") or "alpha —" in lowered or lowered.startswith("alpha\n"):
            return target
        return far

    with patch("locus_agent.skills.embeddings.embed_text", new=AsyncMock(side_effect=_fake_embed)):
        await flush_pending_skill_reindexes()
        matches = await match_skills("polish this paragraph", top_k=1)

    assert matches
    assert matches[0].skill_name == "alpha"


@pytest.mark.asyncio
async def test_create_skill_marks_pending_reindex() -> None:
    delete_skill("alpha")
    delete_skill("beta")
    create_skill(
        Skill(
            name="alpha",
            description="route pending",
            body="body",
            source="private",
        )
    )
    mark_skill_reindex("alpha")

    target = _vec(1.0, 0.0, 0.0)
    far = _vec(0.0, 1.0, 0.0)

    async def _fake_embed(text: str) -> bytes:
        lowered = text.lower()
        if "route pending" in lowered:
            return target
        if lowered.startswith("alpha:") or lowered.startswith("alpha\n"):
            return target
        return far

    with patch("locus_agent.skills.embeddings.embed_text", new=AsyncMock(side_effect=_fake_embed)):
        await flush_pending_skill_reindexes()
        await reindex_all_skills()
        rows = await match_skills("route pending", top_k=1)

    assert rows
    assert rows[0].skill_name == "alpha"


@pytest.mark.asyncio
async def test_build_skill_route_message_injects_required_action() -> None:
    delete_skill("alpha")
    delete_skill("beta")
    create_skill(
        Skill(
            name="alpha",
            description="humanize and polish writing",
            body="## When to use\n\nPolish drafts.",
            source="private",
        )
    )

    target = _vec(1.0, 0.0, 0.0)
    far = _vec(0.0, 1.0, 0.0)

    async def _fake_embed(text: str) -> bytes:
        lowered = text.lower()
        if "polish this paragraph" in lowered:
            return target
        if lowered.startswith("alpha:") or "alpha —" in lowered or lowered.startswith("alpha\n"):
            return target
        return far

    with patch("locus_agent.skills.embeddings.embed_text", new=AsyncMock(side_effect=_fake_embed)):
        await flush_pending_skill_reindexes()
        await reindex_all_skills()
        msg = await build_skill_route_message("polish this paragraph")

    assert msg is not None
    assert "Skill router" in msg
    assert 'skill_view{name: "alpha"}' in msg
