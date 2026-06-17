"""Skill 目录文件与 skill_view 渐进加载测试。"""

from __future__ import annotations

import pytest

from agentpod_agent.db import init_db
from agentpod_agent.skills import (
    Skill,
    create_skill,
    delete_skill,
    list_skill_files,
    read_skill_file,
    resolve_skill_file,
)
from agentpod_agent.skills.fs import format_skill_file_tree
from agentpod_agent.tools.base import ToolError
from agentpod_agent.tools.skills import _skill_view
from agentpod_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db() -> None:
    set_workspace_id(WS_TEST)
    init_db()


def _create_demo_skill(name: str = "demo-skill") -> None:
    delete_skill(name)
    create_skill(
        Skill(
            name=name,
            description="demo",
            body="Use references/guide.md when needed.",
            triggers=["demo"],
            source="private",
        )
    )
    root = resolve_skill_file("demo-skill", "SKILL.md").parent
    refs = root / "references"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "guide.md").write_text("# Guide\n\nStep one.\n", encoding="utf-8")
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "run.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")


def test_list_skill_files_includes_nested_paths() -> None:
    _create_demo_skill()
    paths = {entry.path for entry in list_skill_files("demo-skill") if not entry.is_dir}
    assert "SKILL.md" in paths
    assert "references/guide.md" in paths
    assert "scripts/run.sh" in paths


def test_read_skill_file_returns_text() -> None:
    _create_demo_skill()
    text = read_skill_file("demo-skill", "references/guide.md")
    assert "Step one." in text


def test_resolve_skill_file_rejects_traversal() -> None:
    _create_demo_skill()
    with pytest.raises(ValueError, match="invalid path"):
        resolve_skill_file("demo-skill", "../etc/passwd")


@pytest.mark.asyncio
async def test_skill_view_with_file_path() -> None:
    _create_demo_skill()
    result = await _skill_view({"name": "demo-skill", "file_path": "references/guide.md"})
    assert "Step one." in result.content
    assert "demo-skill/references/guide.md" in result.content


@pytest.mark.asyncio
async def test_skill_view_skill_md_lists_other_files() -> None:
    _create_demo_skill()
    result = await _skill_view({"name": "demo-skill"})
    assert "Use references/guide.md" in result.content
    assert "references/guide.md" in result.content
    assert "scripts/run.sh" in result.content


@pytest.mark.asyncio
async def test_skill_view_rejects_traversal() -> None:
    _create_demo_skill()
    with pytest.raises(ToolError, match="invalid path"):
        await _skill_view({"name": "demo-skill", "file_path": "../SKILL.md"})


def test_format_skill_file_tree_empty_for_skill_md_only() -> None:
    delete_skill("plain")
    create_skill(Skill(name="plain", description="", body="hello", source="private"))
    assert format_skill_file_tree("plain") == ""
