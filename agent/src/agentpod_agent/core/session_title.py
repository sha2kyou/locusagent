"""AI 会话标题生成。"""

from __future__ import annotations

from ..config import get_settings
from ..logging import get_logger
from .llm import get_llm_client
from .openai_fields import openai_completion_text
from ..usage_report import schedule_openai_usage
from .persistence import get_session_title, upsert_session_meta

log = get_logger("session_title")

_TITLE_MAX_LEN = 28


def _is_default_title(title: str | None) -> bool:
    t = (title or "").strip()
    return not t or t == "新对话"


def _sanitize_title(raw: str, *, fallback: str) -> str:
    title = (raw or "").strip()
    title = title.replace("\n", " ").replace("\r", " ")
    title = title.strip("\"'“”‘’` ")
    if not title:
        title = fallback
    if len(title) > _TITLE_MAX_LEN:
        title = title[:_TITLE_MAX_LEN].rstrip()
    return title or "新对话"


async def maybe_generate_and_update_session_title(
    session_id: str,
    *,
    user_query: str,
    assistant_text: str,
    model: str | None = None,
) -> str | None:
    query = (user_query or "").strip()
    answer = (assistant_text or "").strip()
    if not query:
        return None
    current_title = await get_session_title(session_id)
    if not _is_default_title(current_title):
        return current_title

    settings = get_settings()
    from .models import resolve_model

    chosen_model = model or resolve_model("title_generation")
    client = get_llm_client()
    fallback = query.splitlines()[0][:_TITLE_MAX_LEN].strip() or "新对话"
    prompt = (
        "你是会话命名助手。根据下面内容生成一个会话标题。\n"
        "要求：\n"
        "- 中文，8~18 字\n"
        "- 准确概括任务主题\n"
        "- 不要标点、引号、序号\n"
        "- 只输出标题本身"
    )
    content = (
        f"用户问题：{query[:500]}\n"
        f"助手回复：{answer[:800]}"
    )
    try:
        resp = await client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            max_tokens=32,
            temperature=0.2,
        )
        schedule_openai_usage(
            usage=resp.usage,
            scenario="title_generation",
            model=chosen_model,
            session_id=session_id,
        )
        raw_title = openai_completion_text(resp)
        final_title = _sanitize_title(raw_title, fallback=fallback)
        await upsert_session_meta(session_id, title=final_title)
        return final_title
    except Exception as exc:
        # 标题生成失败不影响主流程，回退到首条用户消息裁剪值。
        title = _sanitize_title(fallback, fallback="新对话")
        log.warning("session_title_generate_failed", session_id=session_id, error=str(exc))
        await upsert_session_meta(session_id, title=title)
        return title
