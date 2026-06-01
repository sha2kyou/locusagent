"""对话完成后的记忆自动提取与去重落库。"""

from __future__ import annotations

import json
import re

from ..config import get_settings
from ..memory import add_memory, list_memories
from .llm import get_llm_client
from .openai_fields import openai_completion_text
from ..usage_report import schedule_openai_usage

_REMEMBER_QUERY_MIN_LEN = 4
_REMEMBER_ANSWER_MIN_LEN = 24
_REMEMBER_RECENT_SCAN = 80
_REMEMBER_ANSWER_MAX_LEN = 1200
_REMEMBER_CANDIDATES_MAX = 1
_MEM_KIND_LABELS = {
    "preference": "偏好",
    "constraint": "约束",
    "fact": "事实",
    "goal": "目标",
}
_MEM_KIND_PRIORITY = {
    "constraint": 0,
    "preference": 1,
    "goal": 2,
    "fact": 3,
}


def _normalize_memory_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _normalize_mem_kind(kind: str | None) -> str:
    k = str(kind or "").strip().lower()
    if k in _MEM_KIND_LABELS:
        return k
    return "fact"


def _format_memory_text(kind: str, text: str) -> str:
    label = _MEM_KIND_LABELS.get(kind, _MEM_KIND_LABELS["fact"])
    return f"【{label}】{text.strip()}"


async def _extract_memory_candidates(
    query: str,
    answer: str,
    *,
    model: str | None,
) -> list[dict[str, str]]:
    settings = get_settings()
    from .models import resolve_model

    chosen_model = model or resolve_model("memory_autostore")
    client = get_llm_client()
    prompt = (
        "你是记忆提炼器。请从用户问题和助手回答中提炼对后续对话有长期价值的记忆。"
        "每条记忆只能包含一种类型（preference/constraint/fact/goal），不要混合。"
        "输出严格 JSON：{\"memories\":[{\"kind\":\"preference|constraint|fact|goal\",\"text\":\"...\"}]}"
        "最多1条，每条中文不超过60字。"
        "如果没有可保存记忆，返回 {\"memories\":[]}。"
    )
    content = f"用户问题：{query[:500]}\n助手回答：{answer[:1000]}"
    resp = await client.chat.completions.create(
        model=chosen_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
        max_tokens=220,
        temperature=0.1,
    )
    schedule_openai_usage(
        usage=resp.usage,
        scenario="memory_autostore",
        model=chosen_model,
    )
    raw = openai_completion_text(resp)
    raw = raw.strip()
    if not raw:
        return []
    memories: list[dict[str, str]] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            arr = parsed.get("memories")
            if isinstance(arr, list):
                for x in arr:
                    if not isinstance(x, dict):
                        continue
                    text = str(x.get("text") or "").strip()
                    if not text:
                        continue
                    memories.append(
                        {
                            "kind": _normalize_mem_kind(str(x.get("kind") or "")),
                            "text": text,
                        }
                    )
        elif isinstance(parsed, list):
            for x in parsed:
                if not isinstance(x, dict):
                    continue
                text = str(x.get("text") or "").strip()
                if not text:
                    continue
                memories.append(
                    {
                        "kind": _normalize_mem_kind(str(x.get("kind") or "")),
                        "text": text,
                    }
                )
    except json.JSONDecodeError:
        for line in raw.splitlines():
            s = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
            if s:
                memories.append({"kind": "fact", "text": s})
    memories.sort(key=lambda m: _MEM_KIND_PRIORITY.get(_normalize_mem_kind(m.get("kind")), 99))
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in memories:
        text = str(m.get("text") or "").strip()
        if len(text) < 6:
            continue
        text = text[:80].strip()
        kind = _normalize_mem_kind(m.get("kind"))
        key = _normalize_memory_text(f"{kind}:{text}")
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append({"kind": kind, "text": text})
        if len(cleaned) >= _REMEMBER_CANDIDATES_MAX:
            break
    return cleaned


async def maybe_remember(query_raw: str, answer_raw: str, *, model: str | None = None) -> list[int]:
    query = (query_raw or "").strip()
    answer = (answer_raw or "").strip()
    if not query or not answer:
        return []
    if len(query) < _REMEMBER_QUERY_MIN_LEN and len(answer) < _REMEMBER_ANSWER_MIN_LEN:
        return []

    answer = answer[:_REMEMBER_ANSWER_MAX_LEN].strip()
    candidates = await _extract_memory_candidates(query, answer, model=model)
    if not candidates:
        return []

    recent = await list_memories(limit=_REMEMBER_RECENT_SCAN)
    recent_norm = {_normalize_memory_text(str(item.get("content") or "")) for item in recent}
    saved_ids: list[int] = []
    for item in candidates:
        kind = _normalize_mem_kind(item.get("kind"))
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        memory_text = _format_memory_text(kind, text)
        norm = _normalize_memory_text(memory_text)
        if not norm:
            continue
        if norm in recent_norm:
            continue
        if any(norm in r or r in norm for r in recent_norm if r):
            continue
        mid = await add_memory(memory_text, anchor="experience")
        saved_ids.append(mid)
        recent_norm.add(norm)
    return saved_ids
