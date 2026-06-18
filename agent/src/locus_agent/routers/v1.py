"""OpenAI 兼容路由：/v1/chat/completions、/v1/models。

鉴权：X-Internal-Token（HMAC 比对）。
有 session_id 时以 DB 为上下文单一真相源。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..auth import verify_internal_token
from ..host_settings import build_runtime_time_context
from ..core.models import resolve_model
from ..core import (
    append_message,
    build_llm_messages,
    get_attachments_by_ids,
    create_run,
    create_session,
    get_active_run,
    get_last_user_message,
    persist_openai_message,
    run_chat_loop,
    session_lock,
    link_message_attachments,
    truncate_after_last_user,
    update_run,
    upsert_session_meta,
)
from ..core.persistence import (
    build_persisted_user_message_text,
    _compose_user_content_with_attachments,
)
from ..core.post_run import schedule_post_run
from ..core.run_manager import (
    detach_run_subscriber,
    reconcile_session_active_handles,
    start_stream_run,
)
from ..core.run_sse import iter_run_sse
from ..core.session_title import schedule_session_title_generation
from ..core.system_prompt import get_or_create_system_prompt as _get_or_create_system_prompt
from ..skills.router import build_skill_route_message
from ..logging import get_logger
from ..activity import record_activity
from ..workspace import get_workspace_id
from ..workspace_runtime import ensure_mcp_tools_for_chat, ensure_workspace_context
from .v1_sessions import router as sessions_router

router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(verify_internal_token)])
router.include_router(sessions_router)
log = get_logger("v1")
_background_tasks: set[asyncio.Task] = set()

PUBLIC_API_MODEL_ID = "locusagent-v1"


async def _resolve_v1_model(requested: str | None) -> tuple[str, str]:
    """对外模型 id 与内部 LLM 模型名分离。"""
    if requested not in (None, "", PUBLIC_API_MODEL_ID):
        raise ValueError(f"unsupported model; use {PUBLIC_API_MODEL_ID!r} or omit")
    return PUBLIC_API_MODEL_ID, await resolve_model("main")


def _llm_extra(extra: dict[str, Any] | None) -> dict[str, Any] | None:
    """透传上游参数时禁止客户端覆盖内部 model。"""
    if not extra:
        return None
    sanitized = {k: v for k, v in extra.items() if k != "model"}
    return sanitized or None


async def shutdown_v1_background_tasks(*, timeout_seconds: float = 3.0) -> None:
    pending = [task for task in list(_background_tasks) if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout_seconds)
        except TimeoutError:
            pass
    _background_tasks.clear()


def _schedule_post_run(
    session_id: str,
    *,
    loop_rounds: int,
    model: str | None,
    messages: list[dict[str, Any]] | None,
) -> None:
    schedule_post_run(
        session_id=session_id,
        loop_rounds=loop_rounds,
        model=model,
        messages=messages,
    )


class ChatMessage(BaseModel):
    role: str
    content: Any = None
    attachment_ids: list[str] | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    session_id: str | None = Field(default=None, alias="session_id")
    extra: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}



async def _ensure_session(req: ChatRequest) -> tuple[str, bool]:
    if req.session_id:
        return req.session_id, False
    sid = await create_session()
    return sid, True


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "input_text":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif isinstance(item.get("text"), str) and item.get("text", "").strip():
                    parts.append(str(item["text"]).strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return "\n".join(parts).strip()
    return ""


def _has_image_content(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if item_type in {"image_url", "input_image"}:
            return True
    return False


async def _extract_latest_user_payload(req: ChatRequest) -> tuple[Any, str, str, list[str]] | None:
    for m in reversed(req.messages):
        if m.role != "user":
            continue
        attachment_ids = [str(x).strip() for x in (m.attachment_ids or []) if str(x).strip()]
        text = _extract_text_content(m.content)
        has_image = _has_image_content(m.content)
        if text or has_image or attachment_ids:
            user_query_text = text
            if attachment_ids:
                attachments = await get_attachments_by_ids(attachment_ids)
                if attachments:
                    composed_content = _compose_user_content_with_attachments(text, attachments)
                    if not user_query_text:
                        user_query_text = text or "[attachment]"
                    persisted_text = build_persisted_user_message_text(
                        text,
                        attachments=attachments,
                        attachment_ids=[a["id"] for a in attachments],
                    )
                    return composed_content, persisted_text, user_query_text, [a["id"] for a in attachments]
            if has_image and isinstance(m.content, list):
                user_query_text = user_query_text or "[image attachment]"
                persisted_text = user_query_text
                return m.content, persisted_text, user_query_text, []
            persisted_text = text or ""
            return persisted_text, persisted_text, text, []
    return None


async def _prepare_messages(req: ChatRequest, sid: str) -> tuple[list[dict[str, Any]], str]:
    from ..core.session_review_state import begin_user_turn
    from ..todos.store import delete_session_todos

    latest_user = await _extract_latest_user_payload(req)
    if latest_user is None:
        raise ValueError("missing user message")
    new_user_content, persisted_user_text, user_query_text, attachment_ids = latest_user

    if req.session_id:
        last_db_user = await get_last_user_message(sid)
        if not attachment_ids and last_db_user == user_query_text:
            # 同一句重发即"重新生成 / 失败重试"：先清掉上一轮(可能中断的)助手输出再重跑
            await truncate_after_last_user(sid)
            await delete_session_todos(sid)
        else:
            user_mid = await append_message(sid, "user", persisted_user_text, run_id=None)
            if user_mid > 0 and attachment_ids:
                await link_message_attachments(user_mid, attachment_ids)
        db_msgs = await build_llm_messages(sid)
        # 当前轮若带图片，需要用原始多模态 content 覆盖最后一条用户消息参与 LLM 推理。
        if db_msgs and db_msgs[-1].get("role") == "user":
            db_msgs[-1]["content"] = new_user_content
        user_query = user_query_text or ""
    else:
        db_msgs = [{"role": "user", "content": new_user_content}]
        user_mid = await append_message(sid, "user", persisted_user_text, run_id=None)
        if user_mid > 0 and attachment_ids:
            await link_message_attachments(user_mid, attachment_ids)
        user_query = user_query_text or ""

    if user_query:
        schedule_session_title_generation(sid, user_query=user_query)

    await begin_user_turn(sid)

    system_prompt = await _get_or_create_system_prompt(sid)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    await _insert_runtime_time_context(messages)
    route_msg = await build_skill_route_message(user_query)
    if route_msg:
        messages.append({"role": "system", "content": route_msg})
    messages.extend(db_msgs)
    return messages, user_query


async def _insert_runtime_time_context(messages: list[dict[str, Any]], *, index: int = 1) -> None:
    messages.insert(index, {"role": "system", "content": await build_runtime_time_context()})


async def _persist_loop_messages(
    sid: str,
    final_messages: list[dict],
    initial_len: int,
    *,
    run_id: str,
) -> int | None:
    last_assistant_id: int | None = None
    for msg in final_messages[initial_len:]:
        role = msg.get("role")
        if role not in ("assistant", "tool"):
            continue
        mid = await persist_openai_message(sid, msg, run_id=run_id)
        if role == "assistant":
            last_assistant_id = mid
    return last_assistant_id


@router.post("/chat/completions")
async def chat_completions(req: ChatRequest):
    wid = get_workspace_id()
    await ensure_mcp_tools_for_chat(wid)
    try:
        public_model, internal_model = await _resolve_v1_model(req.model)
    except ValueError as exc:
        return JSONResponse(
            {"error": {"code": "bad_request", "message": str(exc)}},
            status_code=400,
        )
    sid, _ = await _ensure_session(req)

    handle = None
    lock = await session_lock(sid)
    async with lock:
        await reconcile_session_active_handles(sid)
        active = await get_active_run(sid)
        if active is not None:
            return JSONResponse(
                {
                    "error": {
                        "code": "run_in_progress",
                        "message": "session has an active run",
                        "detail": {"run_id": active["id"]},
                    }
                },
                status_code=409,
            )

        try:
            messages, user_query = await _prepare_messages(req, sid)
        except ValueError as exc:
            return JSONResponse(
                {"error": {"code": "bad_request", "message": str(exc)}},
                status_code=400,
            )

        from ..tools import registry

        run_id = await create_run(sid)
        chat_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        initial_len = len(messages)
        record_activity(
            "chat",
            "start",
            f"开始对话（{'流式' if req.stream else '同步'}）",
            workspace_id=wid,
            detail={"session_id": sid, "run_id": run_id, "model": public_model},
        )

        if not req.stream:
            try:
                result, final_messages = await run_chat_loop(
                    messages,
                    registry=registry,
                    model=internal_model,
                    extra=_llm_extra(req.extra),
                    session_id=sid,
                    run_id=run_id,
                )
                last_assistant_id = await _persist_loop_messages(
                    sid, final_messages, initial_len, run_id=run_id
                )
                await update_run(
                    run_id,
                    status="completed",
                    assistant_message_id=last_assistant_id,
                )
                await upsert_session_meta(sid, tokens_delta=result.total_tokens)
                _schedule_post_run(
                    sid,
                    loop_rounds=result.rounds,
                    model=internal_model,
                    messages=final_messages,
                )

                payload = {
                    "id": chat_id,
                    "object": "chat.completion",
                    "created": created,
                    "model": public_model,
                    "session_id": sid,
                    "run_id": run_id,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": result.final_text,
                                "reasoning_content": result.final_reasoning,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"total_tokens": result.total_tokens},
                    "x_tool_calls_made": result.tool_calls_made,
                }
                return JSONResponse(payload)
            except Exception as exc:
                await update_run(run_id, status="failed", error_message=str(exc))
                raise
        else:
            try:
                handle, subscriber = start_stream_run(
                    run_id=run_id,
                    session_id=sid,
                    messages=messages,
                    registry=registry,
                    model=internal_model,
                    extra=_llm_extra(req.extra),
                )
            except Exception as exc:
                await update_run(run_id, status="failed", error_message=str(exc))
                raise

    async def _stream():
        try:
            async for chunk in iter_run_sse(
                subscriber,
                chat_id=chat_id,
                public_model=public_model,
                created=created,
                session_id=sid,
                run_id=run_id,
            ):
                yield chunk
        finally:
            detach_run_subscriber(handle, subscriber)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/models")
async def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": PUBLIC_API_MODEL_ID,
                "object": "model",
                "owned_by": "locusagent",
            }
        ],
    }

