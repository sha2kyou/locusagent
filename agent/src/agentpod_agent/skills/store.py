"""私有 Skill 文件 CRUD。

私有目录：/data/skills/{name}/SKILL.md
公共只读，不允许通过此处修改。
"""

from __future__ import annotations

import shutil

import yaml

from ..logging import get_logger
from .loader import Skill, _parse_skill_md, load_all_skills, private_skill_dir

log = get_logger("skill_store")


def _is_valid_skill_name(name: str) -> bool:
    if not name:
        return False
    if name.startswith("."):
        return False
    if "/" in name or "\\" in name:
        return False
    if name in {".", ".."}:
        return False
    return True


def _private_skill_root(name: str):
    if not _is_valid_skill_name(name):
        raise ValueError("invalid skill name")
    base = private_skill_dir().resolve()
    root = (base / name).resolve()
    root.relative_to(base)
    return root


def _serialize(skill: Skill) -> str:
    fm = {
        "name": skill.name,
        "description": skill.description,
        "triggers": skill.triggers,
    }
    return f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()}\n---\n\n{skill.body.strip()}\n"


def list_skills() -> list[Skill]:
    return load_all_skills()


def get_skill(name: str) -> Skill | None:
    for s in load_all_skills():
        if s.name == name:
            return s
    return None


def create_skill(skill: Skill) -> Skill:
    if not _is_valid_skill_name(skill.name):
        raise ValueError("invalid skill name")
    root = _private_skill_root(skill.name)
    if root.exists():
        raise FileExistsError(f"skill already exists: {skill.name}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(_serialize(skill), encoding="utf-8")
    log.info("skill_created", name=skill.name)
    return skill


def update_skill(name: str, *, description: str | None, body: str | None, triggers: list[str] | None) -> Skill:
    root = _private_skill_root(name)
    file = root / "SKILL.md"
    if not file.is_file():
        raise FileNotFoundError(f"private skill not found: {name}")
    current = _parse_skill_md(file, "private")
    if current is None:
        raise RuntimeError("failed to parse current skill")
    new = Skill(
        name=name,
        description=description if description is not None else current.description,
        body=body if body is not None else current.body,
        triggers=triggers if triggers is not None else current.triggers,
        source="private",
        path=str(file),
    )
    file.write_text(_serialize(new), encoding="utf-8")
    log.info("skill_updated", name=name)
    return new


def delete_skill(name: str) -> bool:
    root = _private_skill_root(name)
    if not root.exists():
        return False
    shutil.rmtree(root)
    log.info("skill_deleted", name=name)
    return True
