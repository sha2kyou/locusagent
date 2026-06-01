"""OpenAI 兼容路由：/v1/chat/completions、/v1/responses、/v1/models。

鉴权：X-Internal-Token（HMAC 比对）。
有 session_id 时以 DB 为上下文单一真相源。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..auth import verify_internal_token
from ..config import get_settings
from ..host_settings import build_runtime_time_context
from ..core import (
    append_message,
    build_llm_messages,
    get_attachments_by_ids,
    create_response,
    create_run,
    create_session,
    get_active_run,
    get_last_user_message,
    get_response,
    get_response_session_id,
    maybe_generate_and_update_session_title,
    persist_openai_message,
    run_chat_loop,
    session_lock,
    link_message_attachments,
    truncate_after_last_user,
    update_run,
    upsert_session_meta,
)
from ..core.memory_autostore import maybe_remember
from ..core.post_run import run_post_tasks
from ..core.run_manager import ERROR, FINISHED, reconcile_session_active_handles, start_stream_run
from ..core.system_prompt import get_or_create_system_prompt as _get_or_create_system_prompt
from ..logging import get_logger
from ..memory import enqueue_embedding
from .v1_sessions import router as sessions_router

router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(verify_internal_token)])
router.include_router(sessions_router)
log = get_logger("v1")
_background_tasks: set[asyncio.Task] = set()


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


def _schedule_remember(user_query: str, final_text: str, *, model: str | None) -> None:
    async def _run() -> None:
        try:
            mids = await maybe_remember(user_query, final_text, model=model)
            for mid in mids:
                await enqueue_embedding(mid)
        except Exception as exc:
            log.warning("memory_autostore_failed", error=str(exc))

    task = asyncio.create_task(_run(), name="memory-autostore")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _schedule_post_run(
    session_id: str,
    *,
    tool_calls_made: int,
    model: str | None,
    messages: list[dict[str, Any]] | None,
) -> None:
    task = asyncio.create_task(
        run_post_tasks(
            session_id=session_id,
            tool_calls_made=tool_calls_made,
            model=model,
            messages=messages,
        ),
        name="post-run",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
_TITLE_MAX_LEN = 28


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


class ResponsesRequest(BaseModel):
    model: str | None = None
    input: Any
    stream: bool = False
    instructions: str | None = None
    previous_response_id: str | None = None
    extra: dict[str, Any] | None = None


def _tool_kind(name: str | None) -> str:
    n = (name or "").lower()
    if n.startswith("skill_") or "skill" in n:
        return "skill"
    if n.startswith("mcp_") or "mcp" in n:
        return "mcp"
    if "memory" in n:
        return "memory"
    return "tool"


async def _ensure_session(req: ChatRequest) -> tuple[str, bool]:
    if req.session_id:
        return req.session_id, False
    sid = await create_session(title="新对话")
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


def _extract_new_user_message_from_response_input(raw_input: Any) -> str | None:
    if isinstance(raw_input, str):
        text = raw_input.strip()
        return text or None
    if isinstance(raw_input, list):
        for item in reversed(raw_input):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                role = str(item.get("role") or "")
                if role != "user":
                    continue
                content = _extract_text_content(item.get("content"))
                if content:
                    return content
            role = str(item.get("role") or "")
            if role == "user":
                content = _extract_text_content(item.get("content"))
                if content:
                    return content
    return None


async def _resolve_response_session(req: ResponsesRequest) -> tuple[str, bool]:
    if req.previous_response_id:
        sid = await get_response_session_id(req.previous_response_id)
        if sid:
            return sid, False
        raise ValueError("previous_response_id not found")
    sid = await create_session(title="新对话")
    return sid, True


def _attachment_signature(attachment_ids: list[str]) -> str:
    joined = "\n".join(attachment_ids)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


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
                    has_img_attachment = any(a.get("kind") == "image" and a.get("processable") for a in attachments)
                    if has_img_attachment:
                        parts: list[dict[str, Any]] = [
                            {"type": "text", "text": text or "请结合附件内容回答。"}
                        ]
                        for a in attachments:
                            if a.get("kind") == "image" and a.get("processable") and a.get("imageDataUrl"):
                                parts.append({"type": "image_url", "image_url": {"url": a["imageDataUrl"]}})
                        text_attachments = [a for a in attachments if a.get("kind") == "text" and a.get("processable")]
                        if text_attachments:
                            for i, a in enumerate(text_attachments, start=1):
                                parts.append(
                                    {
                                        "type": "text",
                                        "text": f"[附件 {i}] name={a.get('name')}\n{str(a.get('text') or '')}",
                                    }
                                )
                        composed_content: Any = parts
                    else:
                        parts: list[dict[str, Any]] = [{"type": "text", "text": text or "请结合附件内容回答。"}]
                        text_attachments = [a for a in attachments if a.get("kind") == "text" and a.get("processable")]
                        if text_attachments:
                            for i, a in enumerate(text_attachments, start=1):
                                parts.append(
                                    {
                                        "type": "text",
                                        "text": f"[附件 {i}] name={a.get('name')}\n{str(a.get('text') or '')}",
                                    }
                                )
                        composed_content = parts
                    if not user_query_text:
                        user_query_text = text or "[attachment]"
                    persisted_text = (text or "").strip()
                    sig = _attachment_signature([a["id"] for a in attachments])
                    persisted_text = f"{persisted_text}\n[attachment_ids:{sig}]".strip()
                    return composed_content, persisted_text, user_query_text, [a["id"] for a in attachments]
            if has_image and isinstance(m.content, list):
                user_query_text = user_query_text or "[image attachment]"
                persisted_text = user_query_text
                return m.content, persisted_text, user_query_text, []
            persisted_text = text or ""
            return persisted_text, persisted_text, text, []
    return None


def _title_from_first_user_message(text: str | None) -> str:
    raw = (text or "").strip()
    if not raw:
        return "新对话"
    title = raw.replace("\n", " ").replace("\r", " ").strip()
    title = title.strip("\"'“”‘’` ")
    if len(title) > _TITLE_MAX_LEN:
        title = title[:_TITLE_MAX_LEN].rstrip()
    return title or "新对话"


def _last_user_content(messages: list[dict[str, Any]]) -> str | None:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = str(msg.get("content") or "").strip()
            if content:
                return content
    return None


async def _prepare_messages(req: ChatRequest, sid: str) -> tuple[list[dict[str, Any]], str]:
    latest_user = await _extract_latest_user_payload(req)
    if latest_user is None:
        raise ValueError("missing user message")
    new_user_content, _persisted_user_text, user_query_text, attachment_ids = latest_user

    if req.session_id:
        last_db_user = await get_last_user_message(sid)
        if not attachment_ids and last_db_user == user_query_text:
            # 同一句重发即"重新生成 / 失败重试"：先清掉上一轮(可能中断的)助手输出再重跑
            await truncate_after_last_user(sid)
        else:
            user_mid = await append_message(sid, "user", user_query_text, run_id=None)
            if user_mid > 0 and attachment_ids:
                await link_message_attachments(user_mid, attachment_ids)
        db_msgs = await build_llm_messages(sid)
        # 当前轮若带图片，需要用原始多模态 content 覆盖最后一条用户消息参与 LLM 推理。
        if db_msgs and db_msgs[-1].get("role") == "user":
            db_msgs[-1]["content"] = new_user_content
        user_query = user_query_text or ""
    else:
        db_msgs = [{"role": "user", "content": new_user_content}]
        user_mid = await append_message(sid, "user", user_query_text, run_id=None)
        if user_mid > 0 and attachment_ids:
            await link_message_attachments(user_mid, attachment_ids)
        # 标题留给运行结束后由 LLM 生成（默认 "新对话"），失败时回退首句裁剪
        user_query = user_query_text or ""

    system_prompt = await _get_or_create_system_prompt(sid)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    await _insert_runtime_time_context(messages)
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
    settings = get_settings()
    chosen_model = req.model or settings.llm_model
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

        if not req.stream:
            try:
                result, final_messages = await run_chat_loop(
                    messages,
                    registry=registry,
                    model=chosen_model,
                    extra=req.extra,
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
                if user_query:
                    await maybe_generate_and_update_session_title(
                        sid,
                        user_query=user_query,
                        assistant_text=result.final_text,
                        model=chosen_model,
                    )
                if user_query and result.final_text:
                    try:
                        mids = await maybe_remember(
                            user_query,
                            result.final_text,
                            model=chosen_model,
                        )
                        for mid in mids:
                            await enqueue_embedding(mid)
                    except Exception as exc:
                        log.warning("memory_autostore_failed", error=str(exc))
                _schedule_post_run(
                    sid,
                    tool_calls_made=result.tool_calls_made,
                    model=chosen_model,
                    messages=final_messages,
                )

                payload = {
                    "id": chat_id,
                    "object": "chat.completion",
                    "created": created,
                    "model": chosen_model,
                    "session_id": sid,
                    "run_id": run_id,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": result.final_text},
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
                handle = start_stream_run(
                    run_id=run_id,
                    session_id=sid,
                    messages=messages,
                    registry=registry,
                    model=chosen_model,
                    extra=req.extra,
                    auto_title_user_query=user_query,
                )
            except Exception as exc:
                await update_run(run_id, status="failed", error_message=str(exc))
                raise

    def _chunk(delta: dict[str, Any], **extra_fields: Any) -> str:
        body: dict[str, Any] = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": chosen_model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        body.update(extra_fields)
        return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"

    async def _stream():
        yield _chunk({"role": "assistant"}, session_id=sid, run_id=run_id)
        try:
            stream_final_text = ""
            while True:
                ev = await handle.queue.get()
                t = ev.get("type")
                if t == FINISHED:
                    stream_final_text = str(ev.get("final_text") or "")
                    break
                if t == ERROR:
                    yield _chunk({}, x_event="error", x_message=ev.get("message") or "unknown")
                    break
                if t == "delta":
                    yield _chunk({"content": ev.get("content") or ""})
                elif t == "tool_call":
                    tool_name = str(ev.get("name") or "")
                    kind = ev.get("tool_kind") or _tool_kind(tool_name)
                    yield _chunk(
                        {},
                        x_event="tool_call",
                        x_tool_name=tool_name,
                        x_tool_kind=kind,
                        x_tool_id=ev.get("id"),
                    )
                elif t == "tool_result":
                    yield _chunk(
                        {},
                        x_event="tool_result",
                        x_tool_call_id=ev.get("tool_call_id"),
                        x_tool_name=ev.get("name"),
                        x_preview=ev.get("preview"),
                    )
        except asyncio.CancelledError:
            log.info("sse_disconnected", run_id=run_id, session_id=sid)
            raise

        if user_query and stream_final_text:
            _schedule_remember(user_query, stream_final_text, model=chosen_model)

        done = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": chosen_model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "run_id": run_id,
        }
        yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/responses")
async def responses(req: ResponsesRequest):
    settings = get_settings()
    chosen_model = req.model or settings.llm_model
    if req.stream:
        return JSONResponse(
            {
                "error": {
                    "code": "unsupported_stream",
                    "message": "stream=true is not implemented for /v1/responses yet",
                }
            },
            status_code=400,
        )
    try:
        sid, is_new_session = await _resolve_response_session(req)
    except ValueError as exc:
        return JSONResponse(
            {"error": {"code": "bad_request", "message": str(exc)}},
            status_code=400,
        )

    new_user = _extract_new_user_message_from_response_input(req.input)
    if not new_user:
        return JSONResponse(
            {"error": {"code": "bad_request", "message": "missing user input"}},
            status_code=400,
        )

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

        if is_new_session:
            await append_message(sid, "user", new_user)
            await upsert_session_meta(sid, title=_title_from_first_user_message(new_user))
            db_msgs: list[dict[str, Any]] = [{"role": "user", "content": new_user}]
        else:
            db_msgs = await build_llm_messages(sid)
            if _last_user_content(db_msgs) != new_user:
                await append_message(sid, "user", new_user)
                db_msgs.append({"role": "user", "content": new_user})
        user_query = new_user

        system_prompt = await _get_or_create_system_prompt(sid)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        await _insert_runtime_time_context(messages)
        if req.instructions and req.instructions.strip():
            messages.append(
                {"role": "system", "content": "## Additional Instructions\n" + req.instructions.strip()}
            )
        messages.extend(db_msgs)

        from ..tools import registry

        run_id = await create_run(sid)
        initial_len = len(messages)
        try:
            result, final_messages = await run_chat_loop(
                messages,
                registry=registry,
                model=chosen_model,
                extra=req.extra,
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
            if user_query and result.final_text:
                try:
                    mids = await maybe_remember(
                        user_query,
                        result.final_text,
                        model=chosen_model,
                    )
                    for mid in mids:
                        await enqueue_embedding(mid)
                except Exception as exc:
                    log.warning("memory_autostore_failed", error=str(exc))
            _schedule_post_run(
                sid,
                tool_calls_made=result.tool_calls_made,
                model=chosen_model,
                messages=final_messages,
            )
            response_id = await create_response(
                sid,
                run_id=run_id,
                previous_response_id=req.previous_response_id,
                assistant_message_id=last_assistant_id,
                model=chosen_model,
                input_text=user_query,
                output_text=result.final_text,
                status="completed",
            )
            return JSONResponse(
                {
                    "id": response_id,
                    "object": "response",
                    "model": chosen_model,
                    "status": "completed",
                    "previous_response_id": req.previous_response_id,
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {"type": "output_text", "text": result.final_text},
                            ],
                        }
                    ],
                    "output_text": result.final_text,
                    "usage": {"total_tokens": result.total_tokens},
                    "x_tool_calls_made": result.tool_calls_made,
                    "session_id": sid,
                    "run_id": run_id,
                }
            )
        except Exception as exc:
            await update_run(run_id, status="failed", error_message=str(exc))
            raise


@router.get("/responses/{response_id}")
async def retrieve_response(response_id: str) -> JSONResponse:
    item = await get_response(response_id)
    if item is None:
        return JSONResponse(
            {"error": {"code": "not_found", "message": "response not found"}},
            status_code=404,
        )
    return JSONResponse(
        {
            "id": item["id"],
            "object": "response",
            "model": item.get("model"),
            "status": item.get("status") or "completed",
            "previous_response_id": item.get("previous_response_id"),
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": item.get("output_text") or ""},
                    ],
                }
            ],
            "output_text": item.get("output_text") or "",
            "session_id": item.get("session_id"),
            "run_id": item.get("run_id"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
    )

@router.get("/models")
async def list_models() -> dict:
    settings = get_settings()
    return {
        "object": "list",
        "data": [
            {
                "id": settings.llm_model,
                "object": "model",
                "owned_by": "agentpod",
            }
        ],
    }

