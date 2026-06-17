"""Skill 目录文件与 skill_view 渐进加载测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentpod_agent.db import init_db
from agentpod_agent.skills import (
    Skill,
    create_skill,
    delete_skill,
    list_skill_files,
    read_skill_file,
    read_skill_file_preview,
    resolve_skill_file,
)
from agentpod_agent.skills.fs import format_skill_file_tree
from agentpod_agent.skills.loader import _parse_skill_md
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


def test_read_skill_file_preview_image() -> None:
    _create_demo_skill()
    root = resolve_skill_file("demo-skill", "SKILL.md").parent
    png = root / "assets" / "logo.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    preview = read_skill_file_preview("demo-skill", "assets/logo.png")
    assert preview.kind == "binary"
    assert preview.content_base64
    assert preview.mime_type == "image/png"


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


def test_parse_skill_md_strips_triggers_from_private_file(tmp_path: Path) -> None:
    skill_md = tmp_path / "legacy-skill" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\nname: legacy-skill\ndescription: legacy\ntriggers:\n  - foo\n  - bar\n---\n\nBody.\n",
        encoding="utf-8",
    )
    parsed = _parse_skill_md(skill_md, "private")
    assert parsed is not None
    assert parsed.name == "legacy-skill"
    rewritten = skill_md.read_text(encoding="utf-8")
    assert "triggers:" not in rewritten
    assert "trigger:" not in rewritten
