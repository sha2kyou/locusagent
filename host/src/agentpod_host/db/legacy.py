"""修复从 Postgres 迁来、id 为 BIGINT 且无 AUTOINCREMENT 的 SQLite 表。"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .models import Base

_AUTOINCREMENT_TABLES = (
    "usage_events",
    "notifications",
    "scheduled_tasks",
    "mcp_oauth_credentials",
)


def _needs_autoincrement_fix(conn: Connection, table_name: str) -> bool:
    ddl = conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).scalar_one_or_none()
    if not ddl:
        return False
    upper = ddl.upper()
    return "ID BIGINT" in upper and "AUTOINCREMENT" not in upper


def _drop_table_indexes(conn: Connection, table_name: str) -> None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        for index in table.indexes:
            conn.execute(text(f'DROP INDEX IF EXISTS "{index.name}"'))
    rows = conn.execute(text(f'PRAGMA index_list("{table_name}")')).fetchall()
    for row in rows:
        index_name = row[1]
        if index_name.startswith("sqlite_autoindex"):
            continue
        conn.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))


def _recover_partial_migration(conn: Connection, table_name: str) -> None:
    backup = f"{table_name}__legacy"
    inspector = inspect(conn)
    names = set(inspector.get_table_names())
    if backup not in names:
        return
    if table_name not in names:
        conn.execute(text(f'ALTER TABLE "{backup}" RENAME TO "{table_name}"'))
        return
    live_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
    backup_count = conn.execute(text(f'SELECT COUNT(*) FROM "{backup}"')).scalar_one()
    if live_count == 0 and backup_count > 0:
        _drop_table_indexes(conn, table_name)
        conn.execute(text(f'DROP TABLE "{table_name}"'))
        conn.execute(text(f'ALTER TABLE "{backup}" RENAME TO "{table_name}"'))
        return
    if live_count > 0 and backup_count > 0:
        table = Base.metadata.tables.get(table_name)
        if table is None:
            return
        columns = [col.name for col in table.columns]
        col_list = ", ".join(f'"{name}"' for name in columns)
        conn.execute(
            text(
                f'INSERT OR IGNORE INTO "{table_name}" ({col_list}) '
                f'SELECT {col_list} FROM "{backup}"'
            )
        )
        conn.execute(text(f'DROP TABLE "{backup}"'))


def _repair_autoincrement_table(conn: Connection, table_name: str) -> None:
    table = Base.metadata.tables.get(table_name)
    if table is None:
        return

    _recover_partial_migration(conn, table_name)
    if not _needs_autoincrement_fix(conn, table_name):
        return

    backup = f"{table_name}__legacy"
    conn.execute(text(f'DROP TABLE IF EXISTS "{backup}"'))
    _drop_table_indexes(conn, table_name)
    conn.execute(text(f'ALTER TABLE "{table_name}" RENAME TO "{backup}"'))
    table.create(conn, checkfirst=False)

    columns = [col.name for col in table.columns]
    col_list = ", ".join(f'"{name}"' for name in columns)
    conn.execute(
        text(f'INSERT INTO "{table_name}" ({col_list}) SELECT {col_list} FROM "{backup}"')
    )
    conn.execute(text(f'DROP TABLE "{backup}"'))


def _drop_obsolete_host_tables(conn: Connection) -> None:
    inspector = inspect(conn)
    if "profile" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("profile")}
        if "timezone" in cols:
            row = conn.execute(text('SELECT timezone FROM profile WHERE id = 1')).fetchone()
            if row and row[0]:
                profile_tz = str(row[0]).strip()
                if profile_tz:
                    from agentpod_shared.settings_store import load_settings_document, save_settings_document

                    doc = load_settings_document()
                    if profile_tz != doc.app.timezone:
                        doc.app.timezone = profile_tz
                        save_settings_document(doc)
        conn.execute(text('DROP TABLE IF EXISTS "profile"'))

    conn.execute(text('DROP TABLE IF EXISTS "audit_logs"'))


def repair_legacy_bigint_autoincrement(conn: Connection) -> None:
    if conn.dialect.name != "sqlite":
        return
    inspector = inspect(conn)
    existing = set(inspector.get_table_names())
    conn.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        for table_name in _AUTOINCREMENT_TABLES:
            if table_name not in existing and f"{table_name}__legacy" not in existing:
                continue
            _repair_autoincrement_table(conn, table_name)
        _drop_obsolete_host_tables(conn)
    finally:
        conn.execute(text("PRAGMA foreign_keys=ON"))
