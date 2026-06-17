"""工作区 hook.py 注册上下文。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from . import POST_USER_SUBMIT, register_workspace_hook

HookCallback = Callable[..., Awaitable[None] | None]


class HookRegistrationContext:
    def __init__(self, *, hook_name: str) -> None:
        self.hook_name = hook_name

    def register_post_user_submit(self, callback: HookCallback) -> None:
        register_workspace_hook(
            POST_USER_SUBMIT,
            _wrap_hook_callback(
                callback,
                hook_name=self.hook_name,
            ),
        )


def _wrap_hook_callback(
    callback: HookCallback,
    *,
    hook_name: str,
) -> HookCallback:
    def wrapped(**kwargs: Any) -> Awaitable[None] | None:
        merged = {
            **kwargs,
            "hook_name": hook_name,
        }
        return callback(**merged)

    wrapped.__name__ = getattr(callback, "__name__", "workspace_hook")
    wrapped.__workspace_hook__ = True  # type: ignore[attr-defined]
    wrapped.__hook_name__ = hook_name  # type: ignore[attr-defined]
    return wrapped
