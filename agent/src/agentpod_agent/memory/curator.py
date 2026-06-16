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
    "You are a memory curator. Below is a batch of long-term memory entries (may have duplicates, staleness, or redundancy). "
    "Merge similar items, remove duplicates, discard clearly stale or low long-term value entries, and output a leaner set.\n"
    "Keep: stable user preferences, identity, and constraints first; drop task progress, PR/issue numbers, one-off troubleshooting, "
    "state descriptions stale within seven days.\n"
    "Each entry one semantic fact, declarative sentences (not instructions to yourself), English, max 60 words per item. "
    'Output strict JSON: {"memories":["entry1","entry2"]}. '
    "Result count must be fewer than input count."
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
                {"role": "user", "content": f"{len(items)} entries:\n{numbered}"},
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
