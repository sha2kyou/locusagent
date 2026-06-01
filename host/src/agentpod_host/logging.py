"""结构化日志：屏蔽敏感字段，保留可观测性。"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "llm_api_key",
    "tavily_api_key",
    "s3_secret_key",
    "s3_access_key",
    "agent_api_key",
    "internal_token",
    "access_token",
    "client_secret",
    "encryption_key",
    "session_secret",
    "password",
    "authorization",
}


def _mask_sensitive(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            value = event_dict[key]
            if isinstance(value, str) and value:
                event_dict[key] = f"{value[:4]}...REDACTED"
            else:
                event_dict[key] = "REDACTED"
    return event_dict


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
            _mask_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
