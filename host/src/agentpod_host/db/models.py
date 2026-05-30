"""ORM 模型：users + audit_logs。

P0 通过 SQLAlchemy `metadata.create_all` 启动建表；后续切 alembic。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ContainerStatus(StrEnum):
    ABSENT = "absent"
    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class ProvisionStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)

    agent_api_key_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    llm_base_url: Mapped[str | None] = mapped_column(Text)
    llm_api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    llm_model: Mapped[str] = mapped_column(Text, default="gpt-4o", nullable=False)
    tavily_api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)

    container_id: Mapped[str | None] = mapped_column(Text)
    container_status: Mapped[str] = mapped_column(
        String(16), default=ContainerStatus.ABSENT.value, nullable=False
    )
    internal_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    network_name: Mapped[str | None] = mapped_column(Text)
    volume_name: Mapped[str | None] = mapped_column(Text)

    provision_status: Mapped[str] = mapped_column(
        String(16), default=ProvisionStatus.PENDING.value, nullable=False
    )

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="user")

    __table_args__ = (
        Index("idx_users_provision", "provision_status"),
        UniqueConstraint("github_id", name="uq_users_github_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User | None] = relationship(back_populates="audit_logs")

    __table_args__ = (Index("idx_audit_user_created", "user_id", "created_at"),)
