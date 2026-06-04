"""Agent Core：对话循环、LLM 调用、tool dispatch。"""

from .llm import get_llm_client
from .persistence import (
    append_message,
    build_llm_messages,
    create_response,
    create_run,
    create_session,
    create_attachment,
    delete_session,
    expire_stale_runs,
    get_active_run,
    get_last_user_message,
    get_response,
    get_response_session_id,
    get_session_system_prompt,
    list_messages,
    list_sessions,
    link_message_attachments,
    get_attachments_by_ids,
    persist_openai_message,
    persist_context_compression,
    session_lock,
    set_session_system_prompt,
    truncate_after_last_user,
    update_message,
    update_run,
    upsert_session_meta,
)
from .session_title import finalize_session_title, maybe_generate_and_update_session_title, schedule_session_title_generation

__all__ = [
    "ERROR",
    "FINISHED",
    "append_message",
    "build_llm_messages",
    "cancel_active_run",
    "create_response",
    "create_run",
    "create_session",
    "create_attachment",
    "delete_session",
    "expire_stale_runs",
    "get_active_run",
    "get_last_user_message",
    "get_response",
    "get_response_session_id",
    "get_session_system_prompt",
    "get_llm_client",
    "list_messages",
    "list_sessions",
    "link_message_attachments",
    "get_attachments_by_ids",
    "persist_openai_message",
    "persist_context_compression",
    "run_chat_loop",
    "session_lock",
    "set_session_system_prompt",
    "start_stream_run",
    "truncate_after_last_user",
    "update_message",
    "update_run",
    "upsert_session_meta",
    "maybe_generate_and_update_session_title",
    "schedule_session_title_generation",
]


def __getattr__(name: str):
    if name == "run_chat_loop":
        from .loop import run_chat_loop

        return run_chat_loop
    if name in {"ERROR", "FINISHED", "cancel_active_run", "start_stream_run"}:
        from . import run_manager

        return getattr(run_manager, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
