"""写入来源标记：区分前台手动写入与 Background Review 自动提取。"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

ORIGIN_MANUAL = "manual"
ORIGIN_AUTO_EXTRACT = "auto_extract"

_write_origin: contextvars.ContextVar[str] = contextvars.ContextVar(
    "write_origin",
    default=ORIGIN_MANUAL,
)


def get_write_origin() -> str:
    return _write_origin.get()


def is_auto_extract_write() -> bool:
    return get_write_origin() == ORIGIN_AUTO_EXTRACT


@contextmanager
def write_origin_scope(origin: str) -> Iterator[None]:
    token = _write_origin.set(origin or ORIGIN_MANUAL)
    try:
        yield
    finally:
        _write_origin.reset(token)
