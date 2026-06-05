"""记忆策展：总量超限时，用 LLM 合并/去重/淘汰最旧的 experience 记忆。

保守策略：
- 仅处理 anchor='experience' 的记忆，绝不触碰 identity（用户稳定事实/偏好）。
- 取最旧的一批做合并，仅当 LLM 产出确实更少时才落地（先增后删，避免信息空窗）。
- 任何异常或非缩减结果都放弃本次策展，不做删除。
"""

from __future__ import annotations

import json
from typing import Any

from ..config import get_settings
from ..logging import get_logger
from .queue import enqueue_embedding
from .store import add_memory, count_memories, delete_memory, list_memories

log = get_logger("memory_curator")

_CURATE_SYSTEM_PROMPT = (
    "你是记忆策展器。下面是一批长期记忆条目（可能有重复、过时或冗余）。"
    "请合并同类、去除重复、丢弃明显过时或无长期价值的条目，输出更精简的一组记忆。\n"
    "保留原则：用户稳定偏好、身份与约束优先；丢弃任务进度、合并请求或议题编号、一次性排障结论、"
    "七天内会过时的状态描述。\n"
    "每条只保留一种语义，用陈述句写事实（不是给自己的指令），简体中文，单条不超过 60 字。"
    '输出严格 JSON：{"memories":["条目1","条目2"]}。'
    "结果条数必须少于输入条数。"
)


async def maybe_curate_memories(*, model: str | None = None) -> int:
    """超过上限时执行一次策展，返回净减少的记忆条数（未执行返回 0）。"""
    settings = get_settings()
    total = await count_memories()
    if total <= settings.memory_max_items:
        return 0

    rows = await list_memories(limit=total)
    experience = [r for r in rows if str(r.get("anchor")) != "identity"]
    # list_memories 按 id DESC（新→旧），取最旧的一批
    batch = list(reversed(experience))[: settings.memory_curate_batch]
    if len(batch) < 2:
        return 0

    items = [str(r.get("content") or "").strip() for r in batch]
    items = [t for t in items if t]
    if len(items) < 2:
        return 0

    from ..core.models import resolve_model

    chosen_model = model or await resolve_model("curator")
    from ..core.auxiliary_completion import create_chat_completion
    from ..core.llm import get_llm_client
    from ..core.openai_fields import openai_completion_text

    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
    try:
        resp = await create_chat_completion(
            get_llm_client(),
            model=chosen_model,
            messages=[
                {"role": "system", "content": _CURATE_SYSTEM_PROMPT},
                {"role": "user", "content": f"共 {len(items)} 条：\n{numbered}"},
            ],
            temperature=0.1,
            retry_log_event="curator_disable_thinking_retry",
        )
        from ..usage_report import schedule_openai_usage

        schedule_openai_usage(usage=resp.usage, scenario="curator", model=chosen_model)
    except Exception as exc:
        log.warning("memory_curate_llm_failed", error=str(exc))
        return 0

    raw = openai_completion_text(resp)
    raw = raw.strip()
    if not raw:
        return 0
    try:
        parsed = json.loads(raw)
        merged_raw = parsed.get("memories") if isinstance(parsed, dict) else parsed
    except json.JSONDecodeError:
        log.warning("memory_curate_parse_failed", raw=raw[:200])
        return 0

    if not isinstance(merged_raw, list):
        return 0
    merged: list[str] = []
    seen: set[str] = set()
    for m in merged_raw:
        text = str(m or "").strip()[:80]
        if text and text not in seen:
            seen.add(text)
            merged.append(text)

    # 必须确实缩减，否则放弃（避免无效改写或膨胀）
    if not merged or len(merged) >= len(batch):
        return 0

    # 先增后删：写入合并结果，再删除原批次
    new_ids: list[int] = []
    for text in merged:
        try:
            mid = await add_memory(text, anchor="experience")
            new_ids.append(mid)
            await enqueue_embedding(mid)
        except Exception as exc:
            log.warning("memory_curate_add_failed", error=str(exc))

    if not new_ids:
        return 0

    removed = 0
    for r in batch:
        rid = int(r.get("id") or 0)
        if not rid:
            continue
        try:
            if await delete_memory(rid):
                removed += 1
        except Exception as exc:
            log.warning("memory_curate_delete_failed", id=rid, error=str(exc))

    net = removed - len(new_ids)
    log.info("memory_curated", batch=len(batch), merged=len(merged), removed=removed, net=net)
    return max(0, net)
