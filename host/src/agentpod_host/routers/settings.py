"""用户设置：时区。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..audit import record_event
from ..auth import AuthContext, require_session
from ..db import User, get_session
from ..scheduled_tasks import recalc_user_task_schedules, validate_timezone
from ..usage import UsageSummaryOut, usage_summary_for_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


class TimezoneConfigIn(BaseModel):
    timezone: str = Field(..., min_length=1, max_length=64)


class TimezoneConfigOut(BaseModel):
    timezone: str


@router.get("/usage-summary", response_model=UsageSummaryOut)
async def read_usage_summary(ctx: AuthContext = Depends(require_session)) -> UsageSummaryOut:
    return await usage_summary_for_user(ctx.user.id)


@router.get("/timezone", response_model=TimezoneConfigOut)
async def read_timezone(ctx: AuthContext = Depends(require_session)) -> TimezoneConfigOut:
    return TimezoneConfigOut(timezone=ctx.user.timezone or "UTC")


@router.put("/timezone", response_model=TimezoneConfigOut)
async def save_timezone(
    payload: TimezoneConfigIn,
    request: Request,
    ctx: AuthContext = Depends(require_session),
) -> TimezoneConfigOut:
    try:
        tz = validate_timezone(payload.timezone)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async with get_session() as session:
        stmt = select(User).where(User.id == ctx.user.id)
        db_user = (await session.execute(stmt)).scalar_one()
        db_user.timezone = tz
        await record_event(
            session,
            "timezone.updated",
            user_id=db_user.id,
            detail={"timezone": tz},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    await recalc_user_task_schedules(ctx.user.id)
    return TimezoneConfigOut(timezone=tz)
