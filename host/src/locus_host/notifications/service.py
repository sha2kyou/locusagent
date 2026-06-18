"""用户站内通知：持久化 + 查询。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update

from ..db.models import Notification
from ..db import get_session
from ..workspaces import ensure_default_workspace_row


def _row_to_dict(row: Notification) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "kind": row.kind,
        "category": row.category,
        "title": row.title,
        "body": row.body or "",
        "link": row.link,
        "read": row.read_at is not None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


async def create_notification(
    *,
    workspace_id: str | None = None,
    title: str,
    body: str = "",
    kind: str = "info",
    category: str | None = None,
    link: str | None = None,
) -> dict:
    title = title.strip()
    if not title:
        raise ValueError("title is required")
    kind = kind if kind in {"info", "success", "warning", "error"} else "info"
    category = (category or "").strip() or None
    if not workspace_id:
        workspace_id = (await ensure_default_workspace_row()).id
    async with get_session() as session:
        row = Notification(
            workspace_id=workspace_id,
            kind=kind,
            category=category,
            title=title,
            body=(body or "").strip(),
            link=(link or None),
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        item = _row_to_dict(row)

    count = await unread_count(workspace_id=workspace_id)
    from .hub import hub

    await hub.publish(
        workspace_id,
        {"type": "notification", "item": item, "unread_count": count},
    )
    return item


async def list_notifications(
    *,
    workspace_id: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list[dict]:
    if not workspace_id:
        workspace_id = (await ensure_default_workspace_row()).id
    limit = max(1, min(int(limit), 200))
    async with get_session() as session:
        stmt = select(Notification).where(Notification.workspace_id == workspace_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        rows = (
            await session.execute(
                stmt.order_by(Notification.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        return [_row_to_dict(r) for r in rows]


async def unread_count(*, workspace_id: str | None = None) -> int:
    if not workspace_id:
        workspace_id = (await ensure_default_workspace_row()).id
    async with get_session() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.workspace_id == workspace_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()
        return int(count or 0)


async def mark_read(notification_id: int, *, workspace_id: str | None = None) -> bool:
    if not workspace_id:
        workspace_id = (await ensure_default_workspace_row()).id
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        result = await session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.workspace_id == workspace_id,
            )
            .values(read_at=now)
        )
        return (result.rowcount or 0) > 0


async def mark_all_read(*, workspace_id: str | None = None) -> int:
    if not workspace_id:
        workspace_id = (await ensure_default_workspace_row()).id
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        result = await session.execute(
            update(Notification)
            .where(
                Notification.workspace_id == workspace_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=now)
        )
        return int(result.rowcount or 0)


async def delete_notification(notification_id: int, *, workspace_id: str | None = None) -> bool:
    if not workspace_id:
        workspace_id = (await ensure_default_workspace_row()).id
    async with get_session() as session:
        row = (
            await session.execute(
                select(Notification).where(
                    Notification.id == notification_id,
                    Notification.workspace_id == workspace_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        await session.delete(row)
        return True
