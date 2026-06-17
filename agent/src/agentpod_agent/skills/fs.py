"""Skill 目录内附属文件读写（references/、scripts/ 等）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .store import get_skill

MAX_SKILL_FILE_BYTES = 512 * 1024


@dataclass(slots=True)
class SkillFileEntry:
    path: str
    is_dir: bool
    size: int | None = None

    def to_dict(self) -> dict:
        return {"path": self.path, "is_dir": self.is_dir, "size": self.size}


def _is_hidden(part: str) -> bool:
    return part.startswith(".") or part.startswith("_")


def skill_root(name: str) -> Path:
    skill = get_skill(name)
    if skill is None:
        raise FileNotFoundError(f"skill not found: {name}")
    if not skill.path:
        raise FileNotFoundError(f"skill path unavailable: {name}")
    root = Path(skill.path).parent.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"skill directory missing: {name}")
    return root


def resolve_skill_file(name: str, relative_path: str) -> Path:
    rel_text = str(relative_path or "").strip()
    if not rel_text:
        raise ValueError("path is required")
    rel = Path(rel_text.replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("invalid path")
    root = skill_root(name)
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes skill directory") from exc
    return candidate


def list_skill_files(name: str) -> list[SkillFileEntry]:
    root = skill_root(name)
    entries: list[SkillFileEntry] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(_is_hidden(part) for part in rel.parts):
            continue
        entries.append(
            SkillFileEntry(
                path=rel.as_posix(),
                is_dir=path.is_dir(),
                size=path.stat().st_size if path.is_file() else None,
            )
        )
    return entries


def read_skill_file(name: str, relative_path: str) -> str:
    path = resolve_skill_file(name, relative_path)
    if path.is_dir():
        raise IsADirectoryError(f"not a file: {relative_path}")
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {relative_path}")
    size = path.stat().st_size
    if size > MAX_SKILL_FILE_BYTES:
        raise ValueError(f"file too large (> {MAX_SKILL_FILE_BYTES} bytes)")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        raise ValueError("binary file cannot be displayed as text")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("file is not valid UTF-8 text") from exc


def format_skill_file_tree(name: str) -> str:
    files = list_skill_files(name)
    rel_paths = sorted(
        entry.path for entry in files if not entry.is_dir and entry.path != "SKILL.md"
    )
    if not rel_paths:
        return ""
    lines = ["", "## Files", "Use skill_view with file_path to load these files:"]
    lines.extend(f"- {path}" for path in rel_paths)
    return "\n".join(lines)
