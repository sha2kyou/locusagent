"""用量事件：LLM token 与第三方 API 调用落库与汇总。"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import UsageEvent, get_session

SCENARIO_LABELS: dict[str, str] = {
    "chat": "对话",
    "compression": "上下文压缩",
    "title_generation": "标题生成",
    "curator": "记忆策展",
    "memory_autostore": "记忆自动提取",
    "skill_reflect": "后台自我改进",
    "approval": "写入审查",
    "tavily": "网络搜索",
    "duckduckgo": "网络搜索",
    "jina": "网页阅读",
    "embedding": "向量嵌入",
    "scheduled_run": "定时任务",
}


def scenario_label(scenario: str) -> str:
    return SCENARIO_LABELS.get(scenario, scenario)


class UsageEventIn(BaseModel):
    scenario: str = Field(..., min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=64)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    api_calls: int = Field(default=0, ge=0)


class UsageSummaryRow(BaseModel):
    scenario: str
    label: str
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    api_calls: int
    event_count: int


class UsageSummaryOut(BaseModel):
    items: list[UsageSummaryRow]
    totals: dict[str, int]


async def record_usage_events(
    session: AsyncSession,
    *,
    user_id: int,
    workspace_id: str | None,
    events: list[UsageEventIn],
) -> int:
    if not events:
        return 0
    ws = (workspace_id or "").strip() or None
    for ev in events:
        session.add(
            UsageEvent(
                user_id=user_id,
                workspace_id=ws,
                session_id=(ev.session_id or "").strip() or None,
                scenario=ev.scenario.strip(),
                model=(ev.model or "").strip() or None,
                prompt_tokens=ev.prompt_tokens,
                completion_tokens=ev.completion_tokens,
                total_tokens=ev.total_tokens,
                api_calls=ev.api_calls,
            )
        )
    return len(events)


async def record_usage_event(
    *,
    user_id: int,
    workspace_id: str | None,
    scenario: str,
    model: str | None = None,
    session_id: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    api_calls: int = 0,
) -> None:
    async with get_session() as session:
        await record_usage_events(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
            events=[
                UsageEventIn(
                    scenario=scenario,
                    model=model,
                    session_id=session_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    api_calls=api_calls,
                )
            ],
        )


async def usage_summary_for_user(user_id: int) -> UsageSummaryOut:
    async with get_session() as session:
        stmt = (
            select(
                UsageEvent.scenario,
                func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
                func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
                func.coalesce(func.sum(UsageEvent.total_tokens), 0),
                func.coalesce(func.sum(UsageEvent.api_calls), 0),
                func.count(UsageEvent.id),
            )
            .where(UsageEvent.user_id == user_id)
            .group_by(UsageEvent.scenario)
            .order_by(func.sum(UsageEvent.total_tokens).desc(), UsageEvent.scenario)
        )
        rows = (await session.execute(stmt)).all()

    items: list[UsageSummaryRow] = []
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "api_calls": 0,
        "event_count": 0,
    }
    for scenario, p, c, t, api, cnt in rows:
        p_i, c_i, t_i, api_i, cnt_i = int(p), int(c), int(t), int(api), int(cnt)
        scenario_s = str(scenario)
        items.append(
            UsageSummaryRow(
                scenario=scenario_s,
                label=scenario_label(scenario_s),
                model=None,
                prompt_tokens=p_i,
                completion_tokens=c_i,
                total_tokens=t_i,
                api_calls=api_i,
                event_count=cnt_i,
            )
        )
        totals["prompt_tokens"] += p_i
        totals["completion_tokens"] += c_i
        totals["total_tokens"] += t_i
        totals["api_calls"] += api_i
        totals["event_count"] += cnt_i

    return UsageSummaryOut(items=items, totals=totals)
