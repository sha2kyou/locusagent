"""Skill 加载器：扫描 SKILL.md（YAML frontmatter + Markdown 正文）。

来源：
- 内置/共享：打包 skills 目录（只读）
- 私有：工作区 skills/*/SKILL.md

加载策略：私有同名覆盖共享。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import get_settings
from ..core.write_origin import ORIGIN_AUTO_EXTRACT, ORIGIN_MANUAL
from ..logging import get_logger
from ..workspace import workspace_data_dir

log = get_logger("skills")

FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<fm>.*?)\n---\s*\n(?P<body>.*)$", re.DOTALL)
_DEPRECATED_FRONTMATTER_KEYS = ("trigger", "triggers")


def _clean_frontmatter(fm: dict) -> bool:
    changed = False
    for key in _DEPRECATED_FRONTMATTER_KEYS:
        if key in fm:
            del fm[key]
            changed = True
    return changed


def format_skill_md(fm: dict, body: str) -> str:
    return f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()}\n---\n\n{body.strip()}\n"


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    body: str
    source: str = "private"
    origin: str = ORIGIN_MANUAL
    path: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "origin": self.origin,
            "body": self.body,
        }


def _parse_skill_md(path: Path, source: str, *, migrate: bool | None = None) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("skill_read_failed", path=str(path), error=str(exc))
        return None
    m = FRONTMATTER_RE.match(text)
    fm: dict = {}
    body = text
    if m:
        try:
            fm = yaml.safe_load(m.group("fm")) or {}
        except yaml.YAMLError as exc:
            log.warning("skill_frontmatter_invalid", path=str(path), error=str(exc))
            return None
        body = m.group("body").strip()
        should_migrate = source == "private" if migrate is None else migrate
        if _clean_frontmatter(fm) and should_migrate:
            try:
                path.write_text(format_skill_md(fm, body), encoding="utf-8")
                log.info("skill_frontmatter_migrated", path=str(path), removed="triggers")
            except OSError as exc:
                log.warning("skill_frontmatter_migrate_failed", path=str(path), error=str(exc))

    name = str(fm.get("name") or path.parent.name)
    description = str(fm.get("description") or "")
    origin_raw = str(fm.get("origin") or ORIGIN_MANUAL).strip().lower()
    origin = origin_raw if origin_raw in {ORIGIN_MANUAL, ORIGIN_AUTO_EXTRACT} else ORIGIN_MANUAL
    return Skill(
        name=name,
        description=description,
        body=body,
        source=source,
        origin=origin,
        path=str(path),
    )


def _scan_dir(root: Path, source: str) -> list[Skill]:
    if not root.is_dir():
        return []
    skills: list[Skill] = []
    for skill_md in root.glob("*/SKILL.md"):
        s = _parse_skill_md(skill_md, source)
        if s is not None:
            skills.append(s)
    return skills


def load_all_skills() -> list[Skill]:
    settings = get_settings()
    public = _scan_dir(settings.shared_skills_dir, "public")
    private = _scan_dir(workspace_data_dir() / "skills", "private")
    by_name: dict[str, Skill] = {s.name: s for s in public}
    for s in private:
        by_name[s.name] = s
    skills = list(by_name.values())
    log.info("skills_loaded", public=len(public), private=len(private), total=len(skills))
    return skills


def private_skill_dir() -> Path:
    return workspace_data_dir() / "skills"
