"""OpenAI 兼容路由：/v1/chat/completions、/v1/responses、/v1/models。

鉴权：X-Internal-Token（HMAC 比对）。
有 session_id 时以 DB 为上下文单一真相源。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..auth import verify_internal_token
from ..config import get_settings
from ..core import (
    append_message,
    build_llm_messages,
    create_response,
    create_run,
    create_session,
    get_active_run,
    get_last_user_message,
    get_response,
    get_response_session_id,
    list_messages,
    list_sessions,
    persist_openai_message,
    run_chat_loop,
    session_lock,
    update_run,
    upsert_session_meta,
)
from ..core.run_manager import ERROR, FINISHED, start_stream_run
from ..logging import get_logger
from ..memory import enqueue_embedding, recall
from ..skills import list_skills

router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(verify_internal_token)])
log = get_logger("v1")
_TITLE_MAX_LEN = 28


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
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


def _build_system_prompt(user_query: str) -> tuple[str, list[str]]:
    skills = list_skills()
    triggered = [s for s in skills if s.matches(user_query)]
    settings = get_settings()
    pieces = [
        f"You are an AI agent operating in a sandboxed container for user {settings.user_id}.",
        "Use the provided tools (web_search/web_extract/memory/skill_view/skill_manage/manage_workspace) when appropriate.",
        "Workspace files live under /data/workspace; private skills live under /data/skills.",
        "Do not perform any file CRUD operations: no file read/list/search/create/update/patch/delete in container or workspace.",
        "The user cannot directly retrieve container/server files from the web UI.",
        "By default, do not create or modify files in workspace.",
        "Deliver outputs directly in chat as inline text, code blocks, and step-by-step instructions.",
        "Proactively check reusable skills before implementing. If the request is non-trivial, call skill_view with empty name once to inspect available skills, then open relevant skill(s) with skill_view{name}.",
    ]
    if skills:
        pieces.append("\n## Available Skills Catalog")
        for s in skills:
            triggers = ", ".join(s.triggers[:5]) if s.triggers else "-"
            desc = (s.description or "").strip() or "(no description)"
            pieces.append(f"- {s.name} [{s.source}] triggers: {triggers} · {desc}")
    if triggered:
        pieces.append("\n## Triggered Skills")
        for s in triggered:
            pieces.append(f"### {s.name}\n{s.description}\n\n{s.body}")
    return "\n".join(pieces), [s.name for s in triggered]


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


def _extract_new_user_message(req: ChatRequest) -> str | None:
    for m in reversed(req.messages):
        if m.role == "user" and (m.content or "").strip():
            return m.content.strip()
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


async def _prepare_messages(req: ChatRequest, sid: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    new_user = _extract_new_user_message(req)
    if not new_user:
        raise ValueError("missing user message")

    if req.session_id:
        db_msgs = await build_llm_messages(sid)
        last_db_user = await get_last_user_message(sid)
        if last_db_user != new_user:
            await append_message(sid, "user", new_user)
            db_msgs.append({"role": "user", "content": new_user})
        user_query = new_user
    else:
        db_msgs = [{"role": "user", "content": new_user}]
        await append_message(sid, "user", new_user)
        await upsert_session_meta(sid, title=_title_from_first_user_message(new_user))
        user_query = new_user

    system_prompt, triggered_skills = _build_system_prompt(user_query)
    recalled = await recall(user_query, top_k=5) if user_query else []
    if recalled:
        system_prompt += "\n\n## Recalled Memory\n" + "\n".join(f"- {m}" for m in recalled)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(db_msgs)
    return messages, user_query, triggered_skills


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
async def chat_completions(req: ChatRequest, request: Request):
    settings = get_settings()
    chosen_model = req.model or settings.llm_model
    sid, _ = await _ensure_session(req)

    handle = None
    lock = await session_lock(sid)
    async with lock:
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
            messages, user_query, triggered_skills = await _prepare_messages(req, sid)
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
                        mid = await _maybe_remember(user_query, result.final_text)
                        if mid is not None:
                            await enqueue_embedding(mid)
                    except Exception as exc:
                        log.warning("memory_autostore_failed", error=str(exc))

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
                    "x_triggered_skills": triggered_skills,
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
        for idx, skill_name in enumerate(triggered_skills):
            tool_call_id = f"skill-auto-{idx}"
            yield _chunk(
                {},
                x_event="tool_call",
                x_tool_name=skill_name,
                x_tool_kind="skill",
                x_tool_id=tool_call_id,
            )
            yield _chunk(
                {},
                x_event="tool_result",
                x_tool_call_id=tool_call_id,
                x_preview="已自动匹配并注入技能上下文",
            )
        try:
            while True:
                ev = await handle.queue.get()
                t = ev.get("type")
                if t == FINISHED:
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

        system_prompt, triggered_skills = _build_system_prompt(user_query)
        recalled = await recall(user_query, top_k=5) if user_query else []
        if recalled:
            system_prompt += "\n\n## Recalled Memory\n" + "\n".join(f"- {m}" for m in recalled)

        if req.instructions and req.instructions.strip():
            system_prompt += "\n\n## Additional Instructions\n" + req.instructions.strip()

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
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
                    "x_triggered_skills": triggered_skills,
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


async def _maybe_remember(_query: str, _answer: str) -> int | None:
    return None


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


@router.get("/sessions")
async def get_sessions() -> dict:
    items = await list_sessions(limit=100)
    return {"items": items}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> dict:
    items = await list_messages(session_id)
    return {"items": items}


@router.get("/sessions/{session_id}/active-run")
async def get_session_active_run(session_id: str) -> dict:
    run = await get_active_run(session_id)
    return {"run": run}
