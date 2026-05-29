"""消息向量索引：写入异步 embedding，供 session_recall hybrid 使用。"""

from __future__ import annotations

from typing import Any

from ..db import conn_scope, run_in_thread

EMBED_TEXT_MAX_CHARS = 2000
_EMBEDDABLE_ROLES = frozenset({"user", "assistant"})


def truncate_embed_text(text: str, *, max_chars: int = EMBED_TEXT_MAX_CHARS) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars]


async def fetch_pending_message_ids(limit: int = 100) -> list[int]:
    def _do() -> list[int]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                """
                SELECT id FROM messages
                WHERE embedding_state='pending' AND role IN ('user', 'assistant')
                ORDER BY id ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [int(r[0]) for r in rows]

    return await run_in_thread(_do)


async def get_message_embed_text(message_id: int) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT role, content FROM messages WHERE id=?",
                (message_id,),
            ).fetchone()
            if not row:
                return None
            if str(row["role"] or "") not in _EMBEDDABLE_ROLES:
                return None
            return truncate_embed_text(str(row["content"] or ""))

    return await run_in_thread(_do)


async def write_message_embedding(message_id: int, blob: bytes) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE messages SET embedding=?, embedding_state='ready' WHERE id=?",
                (blob, message_id),
            )

    await run_in_thread(_do)


async def mark_message_embedding_failed(message_id: int) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE messages SET embedding_state='failed' WHERE id=?",
                (message_id,),
            )

    await run_in_thread(_do)


async def mark_message_embedding_skipped(message_id: int) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE messages SET embedding_state='skipped' WHERE id=?",
                (message_id,),
            )

    await run_in_thread(_do)


async def reset_message_embedding(message_id: int) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE messages SET embedding=NULL, embedding_state='pending' WHERE id=?",
                (message_id,),
            )

    await run_in_thread(_do)
