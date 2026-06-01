"""会话/消息持久化（SQLite，单 writer 通过 asyncio.to_thread 串行）。"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import secrets
from typing import Any

from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from ..storage import (
    AttachmentStorageError,
    delete_attachment_objects,
    load_attachment_bytes,
    save_attachment_bytes,
)

log = get_logger("persistence")

_session_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def session_lock(session_id: str) -> asyncio.Lock:
    async with _locks_guard:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[session_id] = lock
        return lock


def _new_session_id() -> str:
    return f"sess_{secrets.token_urlsafe(12)}"


def _new_run_id() -> str:
    return f"run_{secrets.token_urlsafe(10)}"


def _new_response_id() -> str:
    return f"resp_{secrets.token_urlsafe(12)}"


def _new_attachment_id() -> str:
    return f"att_{secrets.token_urlsafe(12)}"


def _decode_data_url(raw: str) -> tuple[str, bytes]:
    if not raw.startswith("data:") or "," not in raw:
        raise ValueError("invalid data url")
    header, b64 = raw.split(",", 1)
    if ";base64" not in header:
        raise ValueError("unsupported image payload")
    mime = header[5:].split(";", 1)[0].strip() or "application/octet-stream"
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid base64 payload") from exc
    return mime, data


def _encode_data_url(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _to_attachment_meta_row(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"] or "附件"),
        "kind": str(row["kind"] or "other"),
        "mimeType": str(row["mime_type"] or "application/octet-stream"),
        "objectKey": str(row["object_key"] or ""),
        "processable": bool(int(row["processable"] or 0)),
        "unsupportedReason": row["unsupported_reason"],
        "truncated": bool(int(row["truncated"] or 0)),
    }


def _hydrate_attachment(meta: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": meta["id"],
        "name": meta["name"],
        "kind": meta["kind"],
        "mimeType": meta["mimeType"],
        "text": None,
        "imageDataUrl": None,
        "processable": bool(meta["processable"]),
        "unsupportedReason": meta["unsupportedReason"],
        "truncated": bool(meta["truncated"]),
    }
    object_key = str(meta.get("objectKey") or "")
    if not object_key or not out["processable"]:
        if not object_key and out["processable"] and out["kind"] in {"text", "image"}:
            out["processable"] = False
            out["unsupportedReason"] = "附件对象不存在"
        return out
    try:
        data = load_attachment_bytes(object_key)
    except AttachmentStorageError as exc:
        log.warning("attachment_load_failed", attachment_id=out["id"], error=str(exc))
        out["processable"] = False
        out["unsupportedReason"] = "附件读取失败"
        return out
    if data is None:
        out["processable"] = False
        out["unsupportedReason"] = "附件对象不存在"
        return out
    if out["kind"] == "text":
        out["text"] = data.decode("utf-8", errors="replace")
    elif out["kind"] == "image":
        out["imageDataUrl"] = _encode_data_url(str(out["mimeType"]), data)
    return out


def _load_message_attachments_map(c: Any, message_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not message_ids:
        return {}
    placeholders = ",".join("?" for _ in message_ids)
    rows = c.execute(
        "SELECT ma.message_id, a.id, a.name, a.kind, a.mime_type, a.object_key, a.object_etag, a.sha256, "
        "a.processable, a.unsupported_reason, a.truncated, ma.order_index "
        "FROM message_attachments ma "
        "JOIN attachments a ON a.id = ma.attachment_id "
        f"WHERE ma.message_id IN ({placeholders}) "
        "ORDER BY ma.message_id ASC, ma.order_index ASC",
        message_ids,
    ).fetchall()
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        mid = int(row["message_id"])
        out.setdefault(mid, []).append(_to_attachment_meta_row(row))
    return out


def _compose_user_content_with_attachments(text: str, attachments: list[dict[str, Any]]) -> Any:
    clean = text.strip()
    if not attachments:
        return clean

    has_image = any(a.get("kind") == "image" and a.get("processable") for a in attachments)
    text_attachments = [a for a in attachments if a.get("kind") == "text" and a.get("processable")]
    unsupported = [a for a in attachments if not a.get("processable")]

    if has_image:
        parts: list[dict[str, Any]] = []
        parts.append({"type": "text", "text": clean or "请结合附件内容回答。"})
        for a in attachments:
            if a.get("kind") == "image" and a.get("processable") and a.get("imageDataUrl"):
                parts.append({"type": "image_url", "image_url": {"url": a["imageDataUrl"]}})
        if text_attachments:
            for i, a in enumerate(text_attachments, start=1):
                parts.append(
                    {"type": "text", "text": f"[附件 {i}] name={a.get('name')}\n{str(a.get('text') or '')}"}
                )
        if unsupported:
            names = ", ".join(str(a.get("name") or "附件") for a in unsupported)
            parts.append({"type": "text", "text": f"另有不可解析附件：{names}。"})
        return parts

    text_parts: list[dict[str, Any]] = []
    text_parts.append({"type": "text", "text": clean or "请结合附件内容回答。"})
    if text_attachments:
        for i, a in enumerate(text_attachments, start=1):
            text_parts.append(
                {"type": "text", "text": f"[附件 {i}] name={a.get('name')}\n{str(a.get('text') or '')}"}
            )
    if unsupported:
        names = ", ".join(str(a.get("name") or "附件") for a in unsupported)
        text_parts.append({"type": "text", "text": f"用户还上传了不可解析附件：{names}。"})
    return text_parts


def _is_legacy_event_meta(tool_calls: Any) -> bool:
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    first = tool_calls[0]
    return isinstance(first, dict) and "event_type" in first


def _is_openai_tool_calls(tool_calls: Any) -> bool:
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    first = tool_calls[0]
    return isinstance(first, dict) and ("function" in first or first.get("type") == "function")


async def create_session(title: str | None = None) -> str:
    sid = _new_session_id()

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO sessions(id, title) VALUES(?, ?)",
                (sid, title or "新对话"),
            )

    await run_in_thread(_do)
    return sid


async def upsert_session_meta(
    session_id: str,
    *,
    title: str | None = None,
    tokens_delta: int = 0,
    status: str | None = None,
) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            updates = ["updated_at = datetime('now')"]
            params: list[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if tokens_delta:
                updates.append("total_tokens = total_tokens + ?")
                params.append(tokens_delta)
            params.append(session_id)
            sql = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"
            c.execute(sql, params)

    await run_in_thread(_do)


STALE_RUN_SECONDS = 600


async def expire_stale_run_ids(
    session_id: str | None = None,
    *,
    max_age_seconds: int = STALE_RUN_SECONDS,
) -> list[str]:
    """将超时 run 标记为 failed，并返回受影响 run_id 列表。"""

    def _do() -> list[str]:
        with conn_scope(load_vec=False) as c:
            if session_id:
                rows = c.execute(
                    "SELECT id FROM runs WHERE session_id=? AND status='running' "
                    "AND updated_at < datetime('now', ?)",
                    (session_id, f"-{int(max_age_seconds)} seconds"),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id FROM runs WHERE status='running' "
                    "AND updated_at < datetime('now', ?)",
                    (f"-{int(max_age_seconds)} seconds",),
                ).fetchall()
            run_ids = [str(r["id"]) for r in rows]
            if not run_ids:
                return []
            placeholders = ",".join("?" for _ in run_ids)
            c.execute(
                "UPDATE runs SET status='failed', error_message='stale run expired', "
                "updated_at=datetime('now') "
                f"WHERE id IN ({placeholders})",
                run_ids,
            )
            return run_ids

    return await run_in_thread(_do)


async def expire_stale_runs(
    session_id: str | None = None,
    *,
    max_age_seconds: int = STALE_RUN_SECONDS,
) -> int:
    """将超时未更新的 running run 标为 failed，返回清理数量。"""
    return len(
        await expire_stale_run_ids(
            session_id,
            max_age_seconds=max_age_seconds,
        )
    )


async def create_run(session_id: str) -> str:
    await expire_stale_runs(session_id)
    run_id = _new_run_id()

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO runs(id, session_id, status) VALUES (?, ?, 'running')",
                (run_id, session_id),
            )

    await run_in_thread(_do)
    return run_id


async def create_response(
    session_id: str,
    *,
    run_id: str | None = None,
    previous_response_id: str | None = None,
    assistant_message_id: int | None = None,
    model: str | None = None,
    input_text: str = "",
    output_text: str = "",
    status: str = "completed",
) -> str:
    response_id = _new_response_id()

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO responses("
                "id, session_id, run_id, previous_response_id, assistant_message_id, "
                "model, input_text, output_text, status"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    response_id,
                    session_id,
                    run_id,
                    previous_response_id,
                    assistant_message_id,
                    model,
                    input_text,
                    output_text,
                    status,
                ),
            )

    await run_in_thread(_do)
    return response_id


async def get_response(response_id: str) -> dict[str, Any] | None:
    def _do() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id, session_id, run_id, previous_response_id, assistant_message_id, "
                "model, input_text, output_text, status, created_at, updated_at "
                "FROM responses WHERE id = ?",
                (response_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    return await run_in_thread(_do)


async def get_response_session_id(response_id: str) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT session_id FROM responses WHERE id = ?",
                (response_id,),
            ).fetchone()
            return str(row["session_id"]) if row else None

    return await run_in_thread(_do)


async def update_run(
    run_id: str,
    *,
    status: str | None = None,
    assistant_message_id: int | None = None,
    error_message: str | None = None,
) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            updates = ["updated_at = datetime('now')"]
            params: list[Any] = []
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if assistant_message_id is not None:
                updates.append("assistant_message_id = ?")
                params.append(assistant_message_id)
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            params.append(run_id)
            c.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id = ?", params)

    await run_in_thread(_do)


async def get_active_run(session_id: str) -> dict[str, Any] | None:
    await expire_stale_runs(session_id)

    def _do() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id, session_id, status, assistant_message_id, error_message, "
                "created_at, updated_at FROM runs "
                "WHERE session_id = ? AND status = 'running' "
                "ORDER BY updated_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            d = dict(row)
            msg_id = d.get("assistant_message_id")
            if msg_id:
                msg = c.execute(
                    "SELECT id, role, content, tool_calls, tool_call_id, created_at "
                    "FROM messages WHERE id = ?",
                    (msg_id,),
                ).fetchone()
                if msg is not None:
                    md = dict(msg)
                    if md.get("tool_calls"):
                        try:
                            md["tool_calls"] = json.loads(md["tool_calls"])
                        except json.JSONDecodeError:
                            md["tool_calls"] = None
                    d["assistant_message"] = md
            return d

    run = await run_in_thread(_do)
    if run is None:
        return None
    return run


async def append_message(
    session_id: str,
    role: str,
    content: str,
    *,
    tool_calls: Any = None,
    tool_call_id: str | None = None,
    run_id: str | None = None,
    tokens: int | None = None,
) -> int:
    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            cur = c.execute(
                "INSERT INTO messages(session_id, role, content, tool_calls, tool_call_id, run_id, tokens) "
                "SELECT ?, ?, ?, ?, ?, ?, ? "
                "WHERE EXISTS(SELECT 1 FROM sessions WHERE id = ?)",
                (
                    session_id,
                    role,
                    content,
                    json.dumps(tool_calls) if tool_calls else None,
                    tool_call_id,
                    run_id,
                    tokens,
                    session_id,
                ),
            )
            return int(cur.lastrowid or 0)

    message_id = await run_in_thread(_do)
    if message_id <= 0:
        return 0
    if role in {"user", "assistant"}:
        from ..memory.queue import enqueue_message_embedding

        await enqueue_message_embedding(message_id)
    else:
        from ..recall.messages import mark_message_embedding_skipped

        await mark_message_embedding_skipped(message_id)
    return message_id


async def create_attachment(
    *,
    session_id: str | None,
    kind: str,
    name: str,
    mime_type: str | None,
    size_bytes: int,
    text_content: str | None,
    image_data_url: str | None,
    processable: bool,
    unsupported_reason: str | None,
    truncated: bool,
) -> dict[str, Any]:
    attachment_id = _new_attachment_id()
    clean_mime = str(mime_type or "").strip() or "application/octet-stream"
    payload: bytes | None = None
    if kind == "text":
        payload = (text_content or "").encode("utf-8")
        if not mime_type:
            clean_mime = "text/plain;charset=utf-8"
    elif kind == "image":
        if image_data_url:
            parsed_mime, decoded = _decode_data_url(image_data_url)
            clean_mime = parsed_mime or clean_mime
            payload = decoded
    elif text_content:
        payload = text_content.encode("utf-8")

    object_key = ""
    object_etag = ""
    content_sha256 = ""
    if payload is not None:
        try:
            uploaded = save_attachment_bytes(
                attachment_id=attachment_id,
                kind=kind,
                name=name,
                mime_type=clean_mime,
                data=payload,
            )
            object_key = uploaded["object_key"]
            object_etag = uploaded["etag"]
            content_sha256 = hashlib.sha256(payload).hexdigest()
        except AttachmentStorageError as exc:
            raise RuntimeError(f"attachment storage upload failed: {exc}") from exc

    def _do() -> dict[str, Any]:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO attachments("
                "id, session_id, kind, name, mime_type, size_bytes, object_key, object_etag, sha256, "
                "processable, unsupported_reason, truncated"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attachment_id,
                    session_id,
                    kind,
                    name,
                    clean_mime,
                    size_bytes,
                    object_key,
                    object_etag,
                    content_sha256,
                    1 if processable else 0,
                    unsupported_reason,
                    1 if truncated else 0,
                ),
            )
            row = c.execute(
                "SELECT id, name, kind, mime_type, object_key, object_etag, sha256, processable, "
                "unsupported_reason, truncated FROM attachments WHERE id = ?",
                (attachment_id,),
            ).fetchone()
            return _to_attachment_meta_row(row)

    try:
        meta = await run_in_thread(_do)
    except Exception:
        if object_key:
            await run_in_thread(delete_attachment_objects, [object_key])
        raise
    return _hydrate_attachment(meta)


async def get_attachments_by_ids(attachment_ids: list[str]) -> list[dict[str, Any]]:
    if not attachment_ids:
        return []

    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            placeholders = ",".join("?" for _ in attachment_ids)
            rows = c.execute(
                "SELECT id, name, kind, mime_type, object_key, object_etag, sha256, processable, "
                "unsupported_reason, truncated "
                f"FROM attachments WHERE id IN ({placeholders})",
                attachment_ids,
            ).fetchall()
            by_id = {str(r["id"]): _to_attachment_meta_row(r) for r in rows}
            out: list[dict[str, Any]] = []
            for aid in attachment_ids:
                item = by_id.get(aid)
                if item:
                    out.append(item)
            return out

    metas = await run_in_thread(_do)
    return await run_in_thread(lambda: [_hydrate_attachment(m) for m in metas])


async def link_message_attachments(message_id: int, attachment_ids: list[str]) -> None:
    if message_id <= 0 or not attachment_ids:
        return

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            row = c.execute("SELECT session_id FROM messages WHERE id = ?", (message_id,)).fetchone()
            session_id = str(row["session_id"]) if row and row["session_id"] else None
            for idx, aid in enumerate(attachment_ids):
                c.execute(
                    "INSERT OR IGNORE INTO message_attachments(message_id, attachment_id, order_index) "
                    "VALUES (?, ?, ?)",
                    (message_id, aid, idx),
                )
                if session_id:
                    c.execute(
                        "UPDATE attachments SET session_id = COALESCE(session_id, ?) WHERE id = ?",
                        (session_id, aid),
                    )

    await run_in_thread(_do)


async def update_message(
    message_id: int,
    *,
    content: str | None = None,
    tool_calls: Any = None,
    tokens: int | None = None,
) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            updates: list[str] = []
            params: list[Any] = []
            if content is not None:
                updates.append("content = ?")
                params.append(content)
            if tool_calls is not None:
                updates.append("tool_calls = ?")
                params.append(json.dumps(tool_calls) if tool_calls else None)
            if tokens is not None:
                updates.append("tokens = ?")
                params.append(tokens)
            if not updates:
                return False
            params.append(message_id)
            sql = f"UPDATE messages SET {', '.join(updates)} WHERE id = ?"
            cur = c.execute(sql, params)
            return (cur.rowcount or 0) > 0

    ok = await run_in_thread(_do)
    if ok and content is not None:
        from ..memory.queue import bump_message_embedding

        await bump_message_embedding(message_id)
    return ok


async def persist_openai_message(
    session_id: str,
    msg: dict[str, Any],
    *,
    run_id: str | None = None,
) -> int:
    role = msg.get("role")
    if role == "assistant":
        return await append_message(
            session_id,
            "assistant",
            str(msg.get("content") or ""),
            tool_calls=msg.get("tool_calls"),
            run_id=run_id,
        )
    if role == "tool":
        return await append_message(
            session_id,
            "tool",
            str(msg.get("content") or ""),
            tool_call_id=str(msg.get("tool_call_id") or ""),
            run_id=run_id,
        )
    if role == "user":
        return await append_message(session_id, "user", str(msg.get("content") or ""), run_id=run_id)
    raise ValueError(f"unsupported role for persist: {role}")


async def persist_context_compression(
    session_id: str,
    *,
    archive_message_ids: list[int],
    summary_text: str,
    mode: str,
    before_tokens: int,
    after_tokens: int,
    run_id: str | None = None,
) -> int:
    """归档中间消息并写入 context_summary（原消息保留，仅标记 archived）。"""
    if not archive_message_ids:
        return 0
    batch_id = f"cmp_{secrets.token_urlsafe(8)}"
    body = summary_text.strip() or "（中间对话已归档；本次未生成可展示摘要）"
    meta = {
        "compression": {
            "mode": mode,
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "archive_batch_id": batch_id,
            "archived_message_ids": archive_message_ids,
        }
    }

    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            c.execute("BEGIN")
            try:
                placeholders = ",".join("?" * len(archive_message_ids))
                c.execute(
                    f"UPDATE messages SET context_state='archived', archive_batch_id=?, "
                    f"archived_at=datetime('now') "
                    f"WHERE session_id=? AND context_state='active' AND id IN ({placeholders})",
                    (batch_id, session_id, *archive_message_ids),
                )
                cur = c.execute(
                    "INSERT INTO messages("
                    "session_id, role, content, tool_calls, run_id, context_state"
                    ") VALUES (?, 'context_summary', ?, ?, ?, 'active')",
                    (
                        session_id,
                        body,
                        json.dumps(meta, ensure_ascii=False),
                        run_id,
                    ),
                )
                c.execute("COMMIT")
                return int(cur.lastrowid or 0)
            except Exception:
                c.execute("ROLLBACK")
                raise

    return await run_in_thread(_do)


async def build_llm_messages(session_id: str) -> list[dict[str, Any]]:
    """从 DB 重建 OpenAI 格式上下文（仅 active 消息；跳过 legacy UI 伪 tool 消息）。"""

    def _do() -> tuple[list[Any], dict[int, list[dict[str, Any]]]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, role, content, tool_calls, tool_call_id "
                "FROM messages WHERE session_id = ? AND context_state = 'active' "
                "ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            mids = [int(r["id"]) for r in rows]
            attachments_meta_map = _load_message_attachments_map(c, mids)
            return rows, attachments_meta_map

    rows, attachments_meta_map = await run_in_thread(_do)
    attachments_map = await run_in_thread(
        lambda: {mid: [_hydrate_attachment(m) for m in metas] for mid, metas in attachments_meta_map.items()}
    )

    out: list[dict[str, Any]] = []
    for r in rows:
            msg_id = int(r["id"])
            role = r["role"]
            content = r["content"] or ""
            tool_calls_raw = r["tool_calls"]
            tool_calls = None
            if tool_calls_raw:
                try:
                    tool_calls = json.loads(tool_calls_raw)
                except json.JSONDecodeError:
                    tool_calls = None

            if role == "context_summary":
                if content:
                    out.append(
                        {
                            "role": "system",
                            "content": "## 历史对话摘要（更早的消息已压缩）\n" + content,
                            "id": msg_id,
                        }
                    )
                continue

            if role == "user":
                attachments = attachments_map.get(msg_id, [])
                out.append(
                    {
                        "role": "user",
                        "content": _compose_user_content_with_attachments(content, attachments),
                        "id": msg_id,
                    }
                )
                continue

            if role == "assistant":
                if _is_legacy_event_meta(tool_calls):
                    continue
                d: dict[str, Any] = {"role": "assistant", "id": msg_id}
                if content:
                    d["content"] = content
                if _is_openai_tool_calls(tool_calls):
                    d["tool_calls"] = tool_calls
                if d.get("content") is not None or d.get("tool_calls"):
                    out.append(d)
                continue

            if role == "tool":
                if _is_legacy_event_meta(tool_calls):
                    if tool_calls and tool_calls[0].get("event_type") == "tool_result":
                        tc_id = tool_calls[0].get("tool_call_id") or ""
                        preview = content or (tool_calls[0].get("preview") or "")
                        if tc_id:
                            out.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": preview,
                                    "id": msg_id,
                                }
                            )
                    continue
                tc_id = r["tool_call_id"] or ""
                if tc_id:
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": content,
                            "id": msg_id,
                        }
                    )
    return out


async def truncate_after_last_user(session_id: str) -> int:
    """删除最后一条 user 消息之后的所有 assistant/tool 消息。

    用于"重新生成 / 失败重试"：流式路径在首个 token 即落库 assistant，
    重跑前需先清掉上一轮(可能是完整或中断的)助手输出，避免历史中残留重复。
    返回删除的消息数。
    """

    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id FROM messages WHERE session_id = ? AND role = 'user' "
                "ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is None:
                return 0
            cur = c.execute(
                "DELETE FROM messages WHERE session_id = ? AND id > ? AND context_state = 'active'",
                (session_id, row["id"]),
            )
            return int(cur.rowcount or 0)

    return await run_in_thread(_do)


async def get_last_user_message(session_id: str) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
                "ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            return str(row["content"]) if row else None

    return await run_in_thread(_do)


async def list_sessions(limit: int = 50) -> list[dict]:
    def _do() -> list[dict]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, title, status, total_tokens, created_at, updated_at "
                "FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def get_session_system_prompt(session_id: str) -> str | None:
    """读取 session 级冻结的 system prompt 快照。"""

    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT system_prompt FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            value = row["system_prompt"]
            return str(value) if value else None

    return await run_in_thread(_do)


async def set_session_system_prompt(session_id: str, system_prompt: str) -> None:
    """写入 session 级冻结的 system prompt 快照（仅首次构建时调用）。"""

    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE sessions SET system_prompt = ? WHERE id = ?",
                (system_prompt, session_id),
            )

    await run_in_thread(_do)


async def get_session_title(session_id: str) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute("SELECT title FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            title = row["title"]
            return str(title) if title is not None else None

    return await run_in_thread(_do)


async def list_messages(session_id: str) -> list[dict]:
    def _do() -> tuple[list[Any], dict[int, list[dict[str, Any]]]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, role, content, tool_calls, tool_call_id, run_id, tokens, created_at, "
                "context_state, archive_batch_id, archived_at "
                "FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            mids = [int(r["id"]) for r in rows]
            attachments_meta_map = _load_message_attachments_map(c, mids)
            return rows, attachments_meta_map

    rows, attachments_meta_map = await run_in_thread(_do)
    attachments_map = await run_in_thread(
        lambda: {mid: [_hydrate_attachment(m) for m in metas] for mid, metas in attachments_meta_map.items()}
    )
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if d.get("tool_calls"):
            try:
                d["tool_calls"] = json.loads(d["tool_calls"])
            except json.JSONDecodeError:
                d["tool_calls"] = None
        d["attachments"] = attachments_map.get(int(d["id"]), [])
        out.append(d)
    return out


async def delete_session(session_id: str) -> bool:
    def _do() -> tuple[bool, list[str]]:
        with conn_scope(load_vec=False) as c:
            attachment_rows = c.execute(
                "SELECT object_key FROM attachments WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            message_rows = c.execute(
                "SELECT id FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            mids = [int(r["id"]) for r in message_rows]
            if mids:
                placeholders = ",".join("?" for _ in mids)
                c.execute(
                    f"DELETE FROM message_attachments WHERE message_id IN ({placeholders})",
                    mids,
                )
            c.execute("DELETE FROM attachments WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM responses WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cur = c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            keys = [str(r["object_key"] or "") for r in attachment_rows]
            return (cur.rowcount or 0) > 0, keys

    deleted, object_keys = await run_in_thread(_do)
    if object_keys:
        await run_in_thread(delete_attachment_objects, object_keys)
    if deleted:
        async with _locks_guard:
            _session_locks.pop(session_id, None)
    return deleted
