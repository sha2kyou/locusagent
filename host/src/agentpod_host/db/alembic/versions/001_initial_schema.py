"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("agent_api_key_hash", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("container_id", sa.Text(), nullable=True),
        sa.Column("container_status", sa.String(length=16), server_default="absent", nullable=False),
        sa.Column("internal_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("network_name", sa.Text(), nullable=True),
        sa.Column("volume_name", sa.Text(), nullable=True),
        sa.Column("provision_status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_active", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_api_key_hash"),
        sa.UniqueConstraint("github_id", name="uq_users_github_id"),
    )
    op.create_index("idx_users_provision", "users", ["provision_status"], unique=False)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_workspaces_user_created", "workspaces", ["user_id", "created_at"], unique=False)
    op.create_index("idx_workspaces_user_default", "workspaces", ["user_id", "is_default"], unique=False)
    op.execute(
        "CREATE UNIQUE INDEX uq_workspaces_user_default_true "
        "ON workspaces(user_id) WHERE is_default = true"
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_user_created", "audit_logs", ["user_id", "created_at"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_notifications_user_ws_created",
        "notifications",
        ["user_id", "workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_notifications_user_ws_unread",
        "notifications",
        ["user_id", "workspace_id", "read_at"],
        unique=False,
    )

    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("schedule_kind", sa.String(length=8), nullable=False),
        sa.Column("cron_expr", sa.Text(), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notify", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=16), nullable=True),
        sa.Column("last_session_id", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_scheduled_tasks_user", "scheduled_tasks", ["user_id", "created_at"], unique=False)
    op.create_index(
        "idx_scheduled_tasks_workspace",
        "scheduled_tasks",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index("idx_scheduled_tasks_due", "scheduled_tasks", ["enabled", "next_run_at"], unique=False)

    op.create_table(
        "usage_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("api_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_usage_user_created", "usage_events", ["user_id", "created_at"], unique=False)
    op.create_index(
        "idx_usage_user_scenario_model",
        "usage_events",
        ["user_id", "scenario", "model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_usage_user_scenario_model", table_name="usage_events")
    op.drop_index("idx_usage_user_created", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("idx_scheduled_tasks_due", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_workspace", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_user", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
    op.drop_index("idx_notifications_user_ws_unread", table_name="notifications")
    op.drop_index("idx_notifications_user_ws_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("idx_audit_user_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.execute("DROP INDEX IF EXISTS uq_workspaces_user_default_true")
    op.drop_index("idx_workspaces_user_default", table_name="workspaces")
    op.drop_index("idx_workspaces_user_created", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index("idx_users_provision", table_name="users")
    op.drop_table("users")
