"""Alembic 迁移辅助测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentpod_host.db.migrate import (
    INITIAL_REVISION,
    _stamp_legacy_database,
    _sync_database_url,
)


def test_sync_database_url_converts_asyncpg_to_psycopg():
    url = "postgresql+asyncpg://agentpod:secret@postgres:5432/agentpod"
    assert _sync_database_url(url) == "postgresql+psycopg://agentpod:secret@postgres:5432/agentpod"


def test_stamp_legacy_database_when_users_exists_without_revision():
    cfg = MagicMock()
    with patch("agentpod_host.db.migrate.create_engine") as mock_engine:
        conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__.return_value = conn
        with patch("agentpod_host.db.migrate._current_revision", return_value=None):
            with patch("agentpod_host.db.migrate._table_exists", side_effect=lambda _c, name: name == "users"):
                with patch("agentpod_host.db.migrate.command.stamp") as mock_stamp:
                    _stamp_legacy_database(cfg, "postgresql+psycopg://x")
                    mock_stamp.assert_called_once_with(cfg, INITIAL_REVISION)


def test_stamp_legacy_database_skips_when_revision_present():
    cfg = MagicMock()
    with patch("agentpod_host.db.migrate.create_engine"):
        with patch("agentpod_host.db.migrate._current_revision", return_value="001"):
            with patch("agentpod_host.db.migrate.command.stamp") as mock_stamp:
                _stamp_legacy_database(cfg, "postgresql+psycopg://x")
                mock_stamp.assert_not_called()
