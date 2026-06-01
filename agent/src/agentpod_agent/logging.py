"""结构化日志：屏蔽敏感字段。"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "internal_token",
    "internal_token",
    "authorization",
    "api_key",
    "password",
}


def _mask(_logger: Any, _name: str, ev: dict[str, Any]) -> dict[str, Any]:
    for k in list(ev.keys()):
        if k.lower() in SENSITIVE_KEYS:
            v = ev[k]
            ev[k] = (f"{v[:4]}...REDACTED" if isinstance(v, str) and v else "REDACTED")
    return ev


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _mask,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
