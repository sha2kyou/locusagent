"""Shared pytest configuration."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("shared/src", "host/src", "agent/src", "sidecar/src"):
    src = ROOT / sub
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

_test_home = tempfile.mkdtemp(prefix="agentpod-test-")
os.environ.setdefault("AGENTPOD_HOME", _test_home)
os.environ.setdefault("AGENTPOD_MONOLITH", "1")
os.environ.setdefault("INTERNAL_TOKEN", "test-internal-token")
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("EMBEDDING_BASE_URL", "local")
os.environ.setdefault("EMBEDDING_MODEL", "test-model")
os.environ.setdefault("HOST_INTERNAL_URL", "http://127.0.0.1:8080")
