"""Agent 生命周期 hook：可注册回调，在固定节点触发。

工作区 hook 存放在 workspaces/<id>/hooks/<name>/hook.py，由 hook_view / hook_manage 管理。
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..config import get_settings
from ..logging import get_logger

log = get_logger("hooks")

POST_USER_SUBMIT = "post_user_submit"

HookCallback = Callable[..., Awaitable[None] | None]

_HOOKS: dict[str, list[HookCallback]] = {}
_WORKSPACE_HOOKS: dict[str, list[HookCallback]] = {}
_INVOKE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class HookReloadStats:
    hooks_loaded: int
    callbacks_registered: int


def register_hook(hook_name: str, callback: HookCallback) -> None:
    _HOOKS.setdefault(hook_name, []).append(callback)


def register_workspace_hook(hook_name: str, callback: HookCallback) -> None:
    _WORKSPACE_HOOKS.setdefault(hook_name, []).append(callback)


def register_post_user_submit(callback: HookCallback) -> None:
    register_hook(POST_USER_SUBMIT, callback)


def workspace_hook_callback_count(hook_name: str = POST_USER_SUBMIT) -> int:
    return len(_WORKSPACE_HOOKS.get(hook_name, []))


def clear_hooks(hook_name: str | None = None) -> None:
    """测试用：清空已注册 hook（含工作区来源）。"""
    if hook_name is None:
        _HOOKS.clear()
        _WORKSPACE_HOOKS.clear()
        return
    _HOOKS.pop(hook_name, None)
    _WORKSPACE_HOOKS.pop(hook_name, None)


def clear_workspace_hooks() -> None:
    _WORKSPACE_HOOKS.clear()


def clear_skill_hooks() -> None:
    """兼容旧调用。"""
    clear_workspace_hooks()


def list_post_user_submit_hooks() -> list[dict[str, str]]:
    """列出已注册的 post_user_submit 回调（调试/观测）。"""
    entries: list[dict[str, str]] = []
    for callback in _HOOKS.get(POST_USER_SUBMIT, []):
        entries.append(
            {
                "origin": "platform",
                "hook_name": "",
                "callback": getattr(callback, "__name__", repr(callback)),
            }
        )
    for callback in _WORKSPACE_HOOKS.get(POST_USER_SUBMIT, []):
        entries.append(
            {
                "origin": "workspace",
                "hook_name": str(getattr(callback, "__hook_name__", "")),
                "callback": getattr(callback, "__name__", repr(callback)),
            }
        )
    return entries


def _hook_timeout_seconds() -> float:
    timeout = float(get_settings().hook_callback_timeout_seconds)
    return max(0.1, timeout)


async def _run_callback(callback: HookCallback, event_name: str, **kwargs: Any) -> None:
    timeout = _hook_timeout_seconds()
    callback_name = getattr(callback, "__name__", repr(callback))
    hook_name = str(kwargs.get("hook_name") or "")

    async def _invoke() -> None:
        if inspect.iscoroutinefunction(callback):
            await callback(**kwargs)
            return

        def _call_sync() -> Any:
            return callback(**kwargs)

        result = await asyncio.to_thread(_call_sync)
        if inspect.isawaitable(result):
            await result

    try:
        await asyncio.wait_for(_invoke(), timeout=timeout)
    except TimeoutError:
        log.warning(
            "hook_callback_timeout",
            hook_event=event_name,
            hook=hook_name,
            callback=callback_name,
            timeout_seconds=timeout,
        )
    except Exception as exc:
        log.warning(
            "hook_callback_failed",
            hook_event=event_name,
            hook=hook_name,
            callback=callback_name,
            error=str(exc),
        )


async def invoke_hook(hook_name: str, **kwargs: Any) -> None:
    with _INVOKE_LOCK:
        callbacks = list(_HOOKS.get(hook_name, [])) + list(_WORKSPACE_HOOKS.get(hook_name, []))
    for callback in callbacks:
        await _run_callback(callback, hook_name, **kwargs)


async def emit_post_user_submit(
    *,
    session_id: str,
    user_message: str,
    user_message_id: int | None = None,
    attachment_ids: list[str] | None = None,
    submit_source: str = "chat",
    is_regenerate: bool = False,
    workspace_id: str | None = None,
) -> None:
    """用户提交被接受后触发 post_user_submit hook。

    submit_source: 提交来源（chat / scheduled）。兼容旧 hook 仍可通过 kwargs['source'] 读取。
    """
    await invoke_hook(
        POST_USER_SUBMIT,
        session_id=session_id,
        user_message=user_message,
        user_message_id=user_message_id,
        attachment_ids=attachment_ids or [],
        submit_source=submit_source,
        source=submit_source,
        is_regenerate=is_regenerate,
        workspace_id=workspace_id,
    )


__all__ = [
    "POST_USER_SUBMIT",
    "HookCallback",
    "HookReloadStats",
    "clear_hooks",
    "clear_skill_hooks",
    "clear_workspace_hooks",
    "emit_post_user_submit",
    "invoke_hook",
    "list_post_user_submit_hooks",
    "register_hook",
    "register_post_user_submit",
    "register_workspace_hook",
    "workspace_hook_callback_count",
]
