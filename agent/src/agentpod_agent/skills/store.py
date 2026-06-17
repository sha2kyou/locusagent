"""私有 Skill 文件 CRUD。

私有目录：工作区 skills/{name}/SKILL.md
"""

from __future__ import annotations

import shutil

from ..logging import get_logger
from ..core.write_origin import ORIGIN_AUTO_EXTRACT, ORIGIN_MANUAL
from .loader import Skill, _parse_skill_md, format_skill_md, load_all_skills, private_skill_dir

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
    }
    if skill.origin and skill.origin != ORIGIN_MANUAL:
        fm["origin"] = skill.origin
    return format_skill_md(fm, skill.body)


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


def update_skill(
    name: str,
    *,
    description: str | None,
    body: str | None,
    origin: str | None = None,
) -> Skill:
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
        source="private",
        origin=origin if origin is not None else current.origin,
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
