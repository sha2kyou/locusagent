"""OpenAI 兼容路由：/v1/chat/completions、/v1/responses、/v1/models。

鉴权：X-Internal-Token（HMAC 比对）。
有 session_id 时以 DB 为上下文单一真相源。
"""

from __future__ import annotations

import asyncio
import json
import re
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
    get_session_system_prompt,
    list_messages,
    list_sessions,
    maybe_generate_and_update_session_title,
    persist_openai_message,
    run_chat_loop,
    session_lock,
    set_session_system_prompt,
    truncate_after_last_user,
    update_run,
    upsert_session_meta,
)
from ..core.llm import get_llm_client
from ..core.post_run import run_post_tasks
from ..core.run_manager import ERROR, FINISHED, start_stream_run
from ..logging import get_logger
from ..memory import add_memory, enqueue_embedding, list_memories
from ..skills import list_skills

router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(verify_internal_token)])
log = get_logger("v1")
_background_tasks: set[asyncio.Task] = set()


def _schedule_remember(user_query: str, final_text: str, *, model: str | None) -> None:
    async def _run() -> None:
        try:
            mids = await _maybe_remember(user_query, final_text, model=model)
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


_SNAPSHOT_MEMORY_LIMIT = 30


async def _build_memory_snapshot() -> list[str]:
    """构建 session 级冻结记忆快照：identity 优先，其后近期 experience，去重。

    不依赖当轮 query；动态按 query 的召回交由 memory(action=recall)/session_recall 工具。
    """
    rows = await list_memories(limit=_SNAPSHOT_MEMORY_LIMIT)
    if not rows:
        return []
    rows_sorted = sorted(rows, key=lambda r: 0 if str(r.get("anchor")) == "identity" else 1)
    out: list[str] = []
    seen: set[str] = set()
    for r in rows_sorted:
        text = str(r.get("content") or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


async def _build_frozen_system_prompt() -> str:
    """构建 session 首次注入的冻结 system prompt。

    - 技能：仅注入紧凑索引；正文由模型按需 skill_view{name} 加载。
    - 记忆：注入冻结快照；回指/引用历史时由模型按需 recall。
    """
    skills = list_skills()
    settings = get_settings()
    pieces = [
        f"You are an AI agent operating in a sandboxed container for user {settings.user_id}.",
        "Use the provided tools (web_search/web_extract/memory/skill_view/skill_manage/manage_workspace/session_recall) when appropriate.",
        "Workspace files live under /data/workspace; private skills live under /data/skills.",
        "Do not perform any file CRUD operations: no file read/list/search/create/update/patch/delete in container or workspace.",
        "The user cannot directly retrieve container/server files from the web UI.",
        "By default, do not create or modify files in workspace.",
        "Deliver outputs directly in chat as inline text, code blocks, and step-by-step instructions.",
        "A compact skills catalog is listed below. When a skill is relevant to the current task, call skill_view{name} to load its full body on demand; do not assume its content.",
        "A frozen long-term memory snapshot is included below. When the user refers to a previous conversation or an earlier conclusion not covered by the snapshot, use memory(action=recall) or session_recall to retrieve it instead of guessing.",
    ]
    if skills:
        pieces.append("\n## Available Skills Catalog")
        for s in skills:
            triggers = ", ".join(s.triggers[:5]) if s.triggers else "-"
            desc = (s.description or "").strip() or "(no description)"
            pieces.append(f"- {s.name} [{s.source}] triggers: {triggers} · {desc}")
    snapshot = await _build_memory_snapshot()
    if snapshot:
        pieces.append("\n## Memory (frozen snapshot)")
        pieces.extend(f"- {m}" for m in snapshot)
    return "\n".join(pieces)


async def _get_or_create_system_prompt(session_id: str) -> str:
    """读取 session 冻结快照；首次缺失时构建并落库，后续复用以保住 prefix cache。"""
    cached = await get_session_system_prompt(session_id)
    if cached:
        return cached
    prompt = await _build_frozen_system_prompt()
    await set_session_system_prompt(session_id, prompt)
    return prompt


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


async def _prepare_messages(req: ChatRequest, sid: str) -> tuple[list[dict[str, Any]], str]:
    new_user = _extract_new_user_message(req)
    if not new_user:
        raise ValueError("missing user message")

    if req.session_id:
        last_db_user = await get_last_user_message(sid)
        if last_db_user == new_user:
            # 同一句重发即"重新生成 / 失败重试"：先清掉上一轮(可能中断的)助手输出再重跑
            await truncate_after_last_user(sid)
        else:
            await append_message(sid, "user", new_user)
        db_msgs = await build_llm_messages(sid)
        user_query = new_user
    else:
        db_msgs = [{"role": "user", "content": new_user}]
        await append_message(sid, "user", new_user)
        # 标题留给运行结束后由 LLM 生成（默认 "新对话"），失败时回退首句裁剪
        user_query = new_user

    system_prompt = await _get_or_create_system_prompt(sid)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(db_msgs)
    return messages, user_query


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
                        mids = await _maybe_remember(
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
                    mids = await _maybe_remember(
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
    chosen_model = model or settings.llm_model
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
    raw = ((resp.choices or [None])[0].message.content if resp.choices else "") or ""
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


async def _maybe_remember(_query: str, _answer: str, *, model: str | None = None) -> list[int]:
    query = (_query or "").strip()
    answer = (_answer or "").strip()
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
