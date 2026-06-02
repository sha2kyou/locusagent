"""AI 会话标题生成。"""

from __future__ import annotations

import re

from ..logging import get_logger
from .auxiliary_completion import create_chat_completion
from .llm import get_llm_client
from .openai_fields import openai_completion_text
from ..usage_report import schedule_openai_usage
from .persistence import get_session_title, upsert_session_meta

log = get_logger("session_title")

_TITLE_MIN_LEN = 4
_TITLE_MAX_LEN = 12

_EDGE_PUNCT_RE = re.compile(
    r'^[\s\-—_·•*#>「」『』\[\]（）()【】{}<>,，.。!！?？:：;；、/\\|\'"`~]+|'
    r'[\s\-—_·•*#>「」『』\[\]（）()【】{}<>,，.。!！?？:：;；、/\\|\'"`~]+$'
)

_TITLE_SYSTEM_PROMPT = (
    "根据用户与助手的对话，生成一个会话标题。\n"
    "必须遵守：\n"
    "1. 只输出标题，不要任何解释、前缀、后缀或标点\n"
    "2. 中文为主，必要时可含英文/数字\n"
    "3. 长度 4~12 个字\n"
    "4. 用名词短语概括任务主题，不要复述用户原句"
)


def _is_default_title(title: str | None) -> bool:
    t = (title or "").strip()
    return not t or t == "新对话"


def _normalize_title(raw: str) -> str:
    lines = (raw or "").strip().splitlines()
    title = (lines[0] if lines else "").strip()
    title = title.replace("\n", " ").replace("\r", " ")
    while True:
        stripped = _EDGE_PUNCT_RE.sub("", title)
        if stripped == title:
            break
        title = stripped
    if len(title) > _TITLE_MAX_LEN:
        title = title[:_TITLE_MAX_LEN]
    if len(title) < _TITLE_MIN_LEN:
        return ""
    return title


async def maybe_generate_and_update_session_title(
    session_id: str,
    *,
    user_query: str,
    assistant_text: str,
) -> str | None:
    query = (user_query or "").strip()
    if not query:
        return None
    current_title = await get_session_title(session_id)
    if not _is_default_title(current_title):
        return current_title

    from .models import resolve_model

    chosen_model = await resolve_model("title_generation")
    messages = [
        {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"用户：{query[:500]}\n助手：{(assistant_text or '')[:800]}",
        },
    ]
    try:
        resp = await create_chat_completion(
            get_llm_client(),
            model=chosen_model,
            messages=messages,
            temperature=0.1,
            retry_log_event="session_title_disable_thinking_retry",
        )
        schedule_openai_usage(
            usage=resp.usage,
            scenario="title_generation",
            model=chosen_model,
            session_id=session_id,
        )
        raw = openai_completion_text(resp)
        title = _normalize_title(raw)
        if not title:
            log.warning(
                "session_title_empty",
                session_id=session_id,
                model=chosen_model,
                raw=raw[:200],
            )
            return None
        await upsert_session_meta(session_id, title=title)
        return title
    except Exception as exc:
        log.warning("session_title_generate_failed", session_id=session_id, error=str(exc))
        return None
