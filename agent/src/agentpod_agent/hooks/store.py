"""工作区级 hook 文件 CRUD：workspaces/<id>/hooks/<name>/hook.py"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..logging import get_logger
from ..workspace import workspace_data_dir

log = get_logger("hook_store")

DEFAULT_HOOK_BODY = '''"""post_user_submit hook."""


def on_user_submit(*, hook_name, user_message, session_id, submit_source, **kwargs):
    """用户消息被接受后、LLM 循环开始前触发。submit_source 为 chat 或 scheduled。"""
    del hook_name, user_message, session_id, submit_source, kwargs


def register(ctx):
    ctx.register_post_user_submit(on_user_submit)
'''


def _is_valid_hook_name(name: str) -> bool:
    if not name:
        return False
    if name.startswith("."):
        return False
    if "/" in name or "\\" in name:
        return False
    if name in {".", ".."}:
        return False
    return True


def workspace_hooks_dir() -> Path:
    return workspace_data_dir() / "hooks"


def hook_root(name: str) -> Path:
    if not _is_valid_hook_name(name):
        raise ValueError("invalid hook name")
    base = workspace_hooks_dir().resolve()
    root = (base / name).resolve()
    root.relative_to(base)
    return root


def hook_file_path(name: str) -> Path:
    return hook_root(name) / "hook.py"


def list_hooks() -> list[str]:
    root = workspace_hooks_dir()
    if not root.is_dir():
        return []
    names: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "hook.py").is_file():
            names.append(child.name)
    return names


def read_hook(name: str) -> str:
    path = hook_file_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"hook not found: {name}")
    return path.read_text(encoding="utf-8")


def create_hook(name: str, body: str | None = None) -> str:
    if not _is_valid_hook_name(name):
        raise ValueError("invalid hook name")
    root = hook_root(name)
    file_path = root / "hook.py"
    if file_path.exists():
        raise FileExistsError(f"hook already exists: {name}")
    root.mkdir(parents=True, exist_ok=True)
    content = (body if body is not None else DEFAULT_HOOK_BODY).strip() + "\n"
    file_path.write_text(content, encoding="utf-8")
    log.info("hook_created", name=name)
    return content


def update_hook(name: str, body: str) -> str:
    path = hook_file_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"hook not found: {name}")
    content = body.strip() + "\n"
    path.write_text(content, encoding="utf-8")
    log.info("hook_updated", name=name)
    return content


def delete_hook(name: str) -> bool:
    root = hook_root(name)
    if not root.exists():
        return False
    shutil.rmtree(root)
    log.info("hook_deleted", name=name)
    return True
