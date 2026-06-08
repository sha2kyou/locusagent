"""SQLite schema repair."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from agentpod_host.db.legacy import repair_legacy_bigint_autoincrement
from agentpod_host.db.models import Base


def test_repair_bigint_autoincrement_allows_inserts(tmp_path: Path) -> None:
    db_path = tmp_path / "host.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE usage_events (
            id BIGINT NOT NULL PRIMARY KEY,
            workspace_id TEXT,
            session_id TEXT,
            scenario TEXT NOT NULL,
            model TEXT,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            api_calls INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO usage_events (id, scenario) VALUES (1, 'seed')"
    )
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        repair_legacy_bigint_autoincrement(connection)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO usage_events (scenario, prompt_tokens, completion_tokens, total_tokens, api_calls) "
        "VALUES ('chat', 0, 0, 0, 0)"
    )
    row = conn.execute("SELECT id, scenario FROM usage_events ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 2
    assert row[1] == "chat"
