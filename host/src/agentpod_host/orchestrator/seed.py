"""把仓库 shared-skills/ 的内容同步进 named volume，供用户容器只读挂载。

链路：
  仓库 ./shared-skills/        (compose bind, ro)
        → host:/seed/shared-skills
  host:/srv/shared-skills      (named volume)
        → user:/app/skills    (compose bind, ro)

宿主每次启动幂等重置目标目录，保证仓库中的最新模板被分发到所有用户容器。
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

from ..logging import get_logger

log = get_logger("seed")

SEED_SRC = Path("/seed/shared-skills")
SEED_DST = Path("/srv/shared-skills")


def _clear_dir(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def _ensure_world_readable(root: Path) -> None:
    """同步后修正权限：目录 0755，文件 0644，确保 agent 容器内 uid=10001 可读。"""
    for entry in root.rglob("*"):
        try:
            mode = entry.stat().st_mode
            if entry.is_dir():
                entry.chmod(mode | stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            else:
                entry.chmod(mode | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError as exc:
            log.warning("seed_chmod_failed", path=str(entry), error=str(exc))


def sync_shared_skills() -> int:
    """同步 SEED_SRC → SEED_DST，返回包含 SKILL.md 的子目录数量。

    SEED_SRC 不存在视为禁用（开发态可能直接跑 host 进程，无 bind mount）。
    """
    if not SEED_SRC.is_dir():
        log.info("shared_skills_seed_disabled", src=str(SEED_SRC))
        return 0
    SEED_DST.mkdir(parents=True, exist_ok=True)
    _clear_dir(SEED_DST)

    count = 0
    for skill_dir in SEED_SRC.iterdir():
        if not skill_dir.is_dir():
            continue
        target = SEED_DST / skill_dir.name
        shutil.copytree(skill_dir, target)
        if (target / "SKILL.md").is_file():
            count += 1
    _ensure_world_readable(SEED_DST)
    log.info("shared_skills_seeded", count=count, dst=str(SEED_DST))
    return count
