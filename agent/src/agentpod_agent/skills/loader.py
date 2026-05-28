"""Skill 加载器：扫描 SKILL.md（YAML frontmatter + Markdown 正文）。

来源：
- 公共：/app/skills/*/SKILL.md（只读挂载，宿主提供）
- 私有：/data/skills/*/SKILL.md（用户 volume）

加载策略：私有同名覆盖公共。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import get_settings
from ..logging import get_logger

log = get_logger("skills")

FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<fm>.*?)\n---\s*\n(?P<body>.*)$", re.DOTALL)


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    body: str
    triggers: list[str] = field(default_factory=list)
    source: str = "private"
    path: str | None = None

    def matches(self, query: str) -> bool:
        if not self.triggers:
            return False
        q = query.lower()
        return any(t.lower() in q for t in self.triggers)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "source": self.source,
            "body": self.body,
        }


def _parse_skill_md(path: Path, source: str) -> Skill | None:
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

    name = str(fm.get("name") or path.parent.name)
    description = str(fm.get("description") or "")
    triggers_raw = fm.get("trigger") or fm.get("triggers") or []
    triggers = [str(t) for t in triggers_raw] if isinstance(triggers_raw, list) else []
    return Skill(
        name=name,
        description=description,
        body=body,
        triggers=triggers,
        source=source,
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
    private = _scan_dir(settings.data_dir / "skills", "private")
    by_name: dict[str, Skill] = {s.name: s for s in public}
    for s in private:
        by_name[s.name] = s
    skills = list(by_name.values())
    log.info("skills_loaded", public=len(public), private=len(private), total=len(skills))
    return skills


def private_skill_dir() -> Path:
    return get_settings().data_dir / "skills"
