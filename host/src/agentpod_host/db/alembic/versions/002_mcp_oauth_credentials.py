"""mcp oauth credentials

Revision ID: 002
Revises: 001
Create Date: 2026-06-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_credentials",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("server_name", sa.String(length=128), nullable=False),
        sa.Column("server_url", sa.Text(), nullable=False),
        sa.Column("tokens_enc", sa.LargeBinary(), nullable=True),
        sa.Column("client_info_enc", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "workspace_id", "server_name", name="uq_mcp_oauth_cred"),
    )
    op.create_index(
        "idx_mcp_oauth_cred_user_ws",
        "mcp_oauth_credentials",
        ["user_id", "workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_mcp_oauth_cred_user_ws", table_name="mcp_oauth_credentials")
    op.drop_table("mcp_oauth_credentials")
