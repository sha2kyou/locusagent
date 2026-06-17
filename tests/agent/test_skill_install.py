"""Skill 安装 URL 解析与本地安装测试。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from agentpod_agent.db import init_db
from agentpod_agent.skills import install_skill_from_url
from agentpod_agent.skills.install import analyze_skill_md, locate_skill_dir, parse_install_source
from agentpod_agent.tools.base import ToolError
from agentpod_agent.tools.skills import _skill_install
from agentpod_agent.workspace import set_workspace_id

WS_TEST = "ws_0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _init_test_db() -> None:
    set_workspace_id(WS_TEST)
    init_db()


def _make_skill_zip(root: Path, *, name: str = "zip-skill", subpath: str = "my-skill") -> bytes:
    skill_dir = root / subpath
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: from zip\n---\n\nZip body.\n",
        encoding="utf-8",
    )
    (skill_dir / "references").mkdir(exist_ok=True)
    (skill_dir / "references" / "guide.md").write_text("guide", encoding="utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in root.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())
    return buf.getvalue()


def test_parse_github_shorthand() -> None:
    plan = parse_install_source("github:anthropics/skills/skills/pdf")
    assert plan.kind == "archive"
    assert "codeload.github.com/anthropics/skills" in plan.download_url
    assert plan.subpath == "skills/pdf"


def test_parse_github_tree_url() -> None:
    plan = parse_install_source("https://github.com/anthropics/skills/tree/main/skills/pdf")
    assert plan.kind == "archive"
    assert plan.subpath == "skills/pdf"


def test_parse_github_blob_skill_md() -> None:
    plan = parse_install_source(
        "https://github.com/acme/demo/blob/main/packages/foo/SKILL.md",
    )
    assert plan.kind == "archive"
    assert plan.subpath == "packages/foo"


def test_parse_zip_url() -> None:
    plan = parse_install_source("https://example.com/my-skill.zip")
    assert plan.kind == "archive"
    assert plan.download_url.endswith(".zip")


def test_parse_raw_skill_md_url() -> None:
    plan = parse_install_source(
        "https://raw.githubusercontent.com/acme/demo/main/skills/foo/SKILL.md",
    )
    assert plan.kind == "skill_md"


def test_parse_rejects_generic_md_url() -> None:
    with pytest.raises(ValueError, match="unsupported URL"):
        parse_install_source("https://example.com/docs/guide.md")


def test_analyze_skill_md_requires_frontmatter() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        analyze_skill_md("# Just a readme\n\nHello.\n")


def test_analyze_skill_md_requires_description() -> None:
    with pytest.raises(ValueError, match="description"):
        analyze_skill_md("---\nname: demo\n---\n\nBody text.\n")


def test_analyze_skill_md_accepts_valid() -> None:
    analysis = analyze_skill_md("---\nname: demo\ndescription: test skill\n---\n\nBody text.\n")
    assert analysis.name == "demo"
    assert analysis.description == "test skill"


def test_install_rejects_invalid_skill_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest_root = tmp_path / "installed"
    dest_root.mkdir()
    monkeypatch.setattr(
        "agentpod_agent.skills.install.private_skill_dir",
        lambda: dest_root,
    )
    monkeypatch.setattr(
        "agentpod_agent.skills.install._download_bytes",
        lambda _url: b"# Not a skill\n",
    )
    with pytest.raises(ValueError, match="frontmatter"):
        install_skill_from_url("https://raw.githubusercontent.com/acme/demo/main/foo/SKILL.md")


def test_locate_skill_dir_with_subpath(tmp_path: Path) -> None:
    archive_root = tmp_path / "repo-main"
    skill_dir = archive_root / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\n\nbody\n", encoding="utf-8")
    found = locate_skill_dir(tmp_path, "skills/demo")
    assert found == skill_dir


def test_locate_skill_dir_requires_path_when_multiple(tmp_path: Path) -> None:
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="multiple SKILL.md"):
        locate_skill_dir(tmp_path, None)


def test_install_from_local_zip_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_skill_zip(tmp_path / "src")
    dest_root = tmp_path / "installed"
    dest_root.mkdir()
    monkeypatch.setattr(
        "agentpod_agent.skills.install.private_skill_dir",
        lambda: dest_root,
    )
    monkeypatch.setattr(
        "agentpod_agent.skills.install._download_bytes",
        lambda _url: payload,
    )

    result = install_skill_from_url("https://example.com/demo.zip")
    assert result.name == "zip-skill"
    assert (dest_root / "zip-skill" / "SKILL.md").is_file()
    assert (dest_root / "zip-skill" / "references" / "guide.md").is_file()
    assert result.file_count >= 2


@pytest.mark.asyncio
async def test_skill_install_tool_wraps_errors() -> None:
    with pytest.raises(ToolError, match="only https"):
        await _skill_install({"url": "ftp://bad.example/skill"})


@pytest.mark.asyncio
async def test_skill_install_tool_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_skill_zip(tmp_path / "src", name="tool-skill")
    dest_root = tmp_path / "installed"
    dest_root.mkdir()
    monkeypatch.setattr(
        "agentpod_agent.skills.install.private_skill_dir",
        lambda: dest_root,
    )
    monkeypatch.setattr(
        "agentpod_agent.skills.install._download_bytes",
        lambda _url: payload,
    )

    result = await _skill_install({"url": "https://example.com/tool-skill.zip"})
    assert "tool-skill" in result.content
    assert result.metadata["name"] == "tool-skill"
