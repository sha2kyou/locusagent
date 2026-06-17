"""加载工作区 hooks/<name>/hook.py 并注册到 hook 系统。"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import threading
from pathlib import Path
from types import ModuleType

from ..logging import get_logger
from ..tool_settings import is_hook_enabled
from . import HookReloadStats, POST_USER_SUBMIT, clear_workspace_hooks, workspace_hook_callback_count
from .context import HookRegistrationContext
from .store import hook_file_path, list_hooks

log = get_logger("hook_loader")

_LOADED_MODULE_NAMES: list[str] = []
_RELOAD_LOCK = threading.Lock()


def _unload_loaded_modules() -> None:
    for module_name in _LOADED_MODULE_NAMES:
        sys.modules.pop(module_name, None)
    _LOADED_MODULE_NAMES.clear()


def _module_name(hook_name: str, hook_py: Path) -> str:
    digest = hashlib.sha256(str(hook_py).encode()).hexdigest()[:12]
    safe = "".join(ch if ch.isalnum() else "_" for ch in hook_name)
    return f"agentpod_hook_{safe}_{digest}"


def _load_hook_module(*, hook_name: str, hook_py: Path) -> ModuleType | None:
    module_name = _module_name(hook_name, hook_py)
    spec = importlib.util.spec_from_file_location(module_name, hook_py)
    if spec is None or spec.loader is None:
        log.warning("hook_spec_failed", hook=hook_name, path=str(hook_py))
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    _LOADED_MODULE_NAMES.append(module_name)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        log.warning(
            "hook_import_failed",
            hook=hook_name,
            path=str(hook_py),
            error=str(exc),
        )
        sys.modules.pop(module_name, None)
        if module_name in _LOADED_MODULE_NAMES:
            _LOADED_MODULE_NAMES.remove(module_name)
        return None
    return module


def reload_workspace_hooks() -> HookReloadStats:
    """重新扫描并加载当前工作区的 hook。"""
    with _RELOAD_LOCK:
        clear_workspace_hooks()
        _unload_loaded_modules()

        hooks_loaded = 0
        for hook_name in list_hooks():
            if not is_hook_enabled(hook_name):
                log.info("hook_skipped_disabled", hook=hook_name)
                continue
            hook_py = hook_file_path(hook_name)
            module = _load_hook_module(hook_name=hook_name, hook_py=hook_py)
            if module is None:
                continue
            register_fn = getattr(module, "register", None)
            if not callable(register_fn):
                log.warning("hook_missing_register", hook=hook_name, path=str(hook_py))
                continue
            ctx = HookRegistrationContext(hook_name=hook_name)
            before = workspace_hook_callback_count(POST_USER_SUBMIT)
            try:
                register_fn(ctx)
            except Exception as exc:
                log.warning(
                    "hook_register_failed",
                    hook=hook_name,
                    path=str(hook_py),
                    error=str(exc),
                )
                continue
            after = workspace_hook_callback_count(POST_USER_SUBMIT)
            if after <= before:
                log.warning("hook_register_no_callbacks", hook=hook_name, path=str(hook_py))
                continue
            hooks_loaded += 1
            log.info("hook_loaded", hook=hook_name, path=str(hook_py), callbacks=after - before)

        callbacks_registered = workspace_hook_callback_count(POST_USER_SUBMIT)
        return HookReloadStats(
            hooks_loaded=hooks_loaded,
            callbacks_registered=callbacks_registered,
        )
