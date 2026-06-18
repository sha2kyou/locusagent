"""shared-skills 同步到 ~/.locusagent/skills。"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

from ..logging import get_logger

log = get_logger("seed")


def _resolve_seed_src() -> Path | None:
    try:
        from locus_shared.settings_store import shared_skills_dir

        repo = shared_skills_dir()
        if repo and repo.is_dir():
            return repo
    except ImportError:
        pass
    return None


def _resolve_seed_dst() -> Path:
    from locus_shared.settings_store import data_dir

    return data_dir() / "skills"


def _clear_dir(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def _ensure_world_readable(root: Path) -> None:
    for entry in root.rglob("*"):
        try:
            mode = entry.stat().st_mode
            if entry.is_dir():
                entry.chmod(
                    mode
                    | stat.S_IRUSR
                    | stat.S_IXUSR
                    | stat.S_IRGRP
                    | stat.S_IXGRP
                    | stat.S_IROTH
                    | stat.S_IXOTH
                )
            else:
                entry.chmod(mode | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError as exc:
            log.warning("seed_chmod_failed", path=str(entry), error=str(exc))


def sync_shared_skills() -> int:
    src = _resolve_seed_src()
    if src is None:
        log.info("shared_skills_seed_disabled")
        return 0
    dst = _resolve_seed_dst()
    dst.mkdir(parents=True, exist_ok=True)
    _clear_dir(dst)

    count = 0
    for skill_dir in src.iterdir():
        if not skill_dir.is_dir():
            continue
        target = dst / skill_dir.name
        shutil.copytree(skill_dir, target)
        if (target / "SKILL.md").is_file():
            count += 1
    _ensure_world_readable(dst)
    log.info("shared_skills_seeded", count=count, dst=str(dst))
    return count
