"""子进程环境构建：按需注入 workspace env_vars。"""

from __future__ import annotations

from typing import Any

from locus_shared.workspace_venv import with_workspace_venv_path

from ..env_vars import resolve_env_var_names
from ..subprocess_env import merge_subprocess_env, normalize_env_names, safe_subprocess_env
from ..workspace import get_workspace_id
from .base import ToolError


async def build_proc_env(args: dict[str, Any], *, include_workspace_venv_path: bool = True) -> dict[str, str]:
    env_names = normalize_env_names(args.get("env"))
    try:
        workspace_vars = await resolve_env_var_names(env_names)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if workspace_vars:
        env = merge_subprocess_env(workspace_vars=workspace_vars)
    else:
        env = safe_subprocess_env()
    if include_workspace_venv_path:
        env = with_workspace_venv_path(env, get_workspace_id())
    return env
