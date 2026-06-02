"""Shared pytest configuration."""

from __future__ import annotations

import os

os.environ.setdefault("USER_ID", "1")
os.environ.setdefault("INTERNAL_TOKEN", "test-internal-token")
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("EMBEDDING_MODEL", "test-model")
os.environ.setdefault("HOST_INTERNAL_URL", "http://127.0.0.1:8080")
