"""技能自我改进闭环：任务完成后从轨迹中反思、沉淀可复用技能。

触发：本轮工具调用数达到阈值（settings.skill_reflect_min_tool_calls）。
判定与生成均由 LLM 完成；写入前过安全门；同名则 patch，否则 create。
失败安全：任何异常仅记录日志，不影响主流程。
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import get_settings
from ..db import run_in_thread
from ..logging import get_logger
from ..security import review_write
from .loader import Skill
from .store import create_skill, get_skill, list_skills, update_skill

log = get_logger("skill_reflect")

_REFLECT_SYSTEM_PROMPT = (
    "你是技能提炼器。从一段已完成的任务轨迹中，判断是否存在可复用、非平凡的工作流值得沉淀为技能。"
    "技能应包含步骤、关键命令/工具、易错点与验证方式。"
    "闲聊、一次性简单问答、无明确流程的任务不要沉淀。"
    "若值得沉淀，输出严格 JSON："
    '{"skip": false, "name": "英文小写短横线命名", "description": "一句话", '
    '"triggers": ["关键词"], "body": "Markdown 步骤正文"}；'
    '否则输出 {"skip": true}。'
)


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9\-_]+", "-", s).strip("-")
    return s[:48]


def _build_trajectory(messages: list[dict[str, Any]], *, max_chars: int = 4000) -> str:
    parts: list[str] = []
    for m in messages:
        role = str(m.get("role") or "")
        if role == "system":
            continue
        content = str(m.get("content") or "").strip()
        tool_calls = m.get("tool_calls") or []
        if role == "assistant" and tool_calls:
            names = [
                str((tc.get("function") or {}).get("name") or "")
                for tc in tool_calls
                if isinstance(tc, dict)
            ]
            names = [n for n in names if n]
            if names:
                parts.append(f"[assistant 调用工具] {', '.join(names)}")
        if content:
            parts.append(f"[{role}] {content[:500]}")
    text = "\n".join(parts)
    return text[-max_chars:]


async def maybe_distill_skill(messages: list[dict[str, Any]], *, model: str | None = None) -> str | None:
    """从轨迹中尝试沉淀一个技能；返回写入的技能名或 None。"""
    trajectory = _build_trajectory(messages)
    if not trajectory.strip():
        return None

    settings = get_settings()
    from ..core.models import resolve_model

    chosen_model = model or resolve_model("skill_reflect")
    from ..core.completion_limits import MIN_AUXILIARY_COMPLETION_TOKENS
    from ..core.llm import get_llm_client
    from ..core.openai_fields import openai_completion_text

    client = get_llm_client()
    try:
        resp = await client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": _REFLECT_SYSTEM_PROMPT},
                {"role": "user", "content": f"任务轨迹：\n{trajectory}"},
            ],
            max_tokens=MIN_AUXILIARY_COMPLETION_TOKENS,
            temperature=0.2,
        )
        from ..usage_report import schedule_openai_usage

        schedule_openai_usage(usage=resp.usage, scenario="skill_reflect", model=chosen_model)
    except Exception as exc:
        log.warning("skill_reflect_llm_failed", error=str(exc))
        return None

    raw = openai_completion_text(resp)
    raw = raw.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("skill_reflect_parse_failed", raw=raw[:200])
        return None
    if not isinstance(parsed, dict) or parsed.get("skip"):
        return None

    name = _slugify(str(parsed.get("name") or ""))
    description = str(parsed.get("description") or "").strip()
    body = str(parsed.get("body") or "").strip()
    triggers_raw = parsed.get("triggers")
    triggers = [str(t) for t in triggers_raw] if isinstance(triggers_raw, list) else []
    if not name or not body:
        return None

    verdict = await review_write(f"{description}\n\n{body}", kind="skill", source="auto")
    if not verdict.allowed:
        log.warning("skill_reflect_blocked", name=name, reason=verdict.reason)
        return None

    try:
        existing_names = {s.name for s in await run_in_thread(list_skills)}
        if name in existing_names:
            current = await run_in_thread(get_skill, name)
            if current is not None and current.source == "public":
                log.info("skill_reflect_skip_public", name=name)
                return None
            await run_in_thread(
                update_skill,
                name,
                description=description or None,
                body=body,
                triggers=triggers or None,
            )
            log.info("skill_reflect_updated", name=name)
        else:
            await run_in_thread(
                create_skill,
                Skill(name=name, description=description, body=body, triggers=triggers, source="private"),
            )
            log.info("skill_reflect_created", name=name)
        return name
    except Exception as exc:
        log.warning("skill_reflect_write_failed", name=name, error=str(exc))
        return None
