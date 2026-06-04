"""scheduled task run tracking fields

Revision ID: 003
Revises: 002
Create Date: 2026-06-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scheduled_tasks", sa.Column("active_run_session_id", sa.Text(), nullable=True))
    op.add_column("scheduled_tasks", sa.Column("last_run_summary", sa.Text(), nullable=True))
    op.add_column(
        "scheduled_tasks",
        sa.Column("active_run_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "active_run_manual")
    op.drop_column("scheduled_tasks", "last_run_summary")
    op.drop_column("scheduled_tasks", "active_run_session_id")
