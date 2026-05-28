"""记忆 CRUD + 召回。

约束：
- 写入时不阻塞：仅入库 content + state=pending，由 embedding worker 异步生成向量。
- 召回：少于 N 条全量注入；否则向量优先；向量不可用退化关键词。
"""

from __future__ import annotations

import struct
from typing import Any

from ..config import get_settings
from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from .embedder import EmbeddingUnavailable, embed_text

log = get_logger("memory")


def _normalize_anchor(anchor: str | None) -> str:
    a = str(anchor or "experience").strip().lower()
    return a if a in {"identity", "experience"} else "experience"


async def add_memory(content: str, *, anchor: str = "experience") -> int:
    if not content or not content.strip():
        raise ValueError("content is empty")
    a = _normalize_anchor(anchor)

    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            cur = c.execute("INSERT INTO memory(content, anchor) VALUES(?, ?)", (content, a))
            return int(cur.lastrowid or 0)

    return await run_in_thread(_do)


async def update_memory(memory_id: int, content: str | None = None, *, anchor: str | None = None) -> bool:
    has_content = content is not None
    has_anchor = anchor is not None
    if not has_content and not has_anchor:
        raise ValueError("nothing to update")
    if has_content and not str(content).strip():
        raise ValueError("content is empty")
    normalized_anchor = _normalize_anchor(anchor) if has_anchor else None

    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            set_parts: list[str] = []
            params: list[Any] = []
            if has_content:
                set_parts.extend(["content=?", "embedding=NULL", "embedding_state='pending'"])
                params.append(str(content))
            if has_anchor:
                set_parts.append("anchor=?")
                params.append(str(normalized_anchor))
            params.append(memory_id)
            sql = f"UPDATE memory SET {', '.join(set_parts)} WHERE id=?"
            cur = c.execute(sql, params)
            return cur.rowcount > 0

    return await run_in_thread(_do)


async def delete_memory(memory_id: int) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            cur = c.execute("DELETE FROM memory WHERE id=?", (memory_id,))
            return cur.rowcount > 0

    return await run_in_thread(_do)


async def list_memories(limit: int = 100) -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, content, anchor, embedding_state, created_at "
                "FROM memory ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def count_memories() -> int:
    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            (n,) = c.execute("SELECT COUNT(*) FROM memory").fetchone()
            return int(n)

    return await run_in_thread(_do)


async def fetch_pending_ids(limit: int = 50) -> list[int]:
    def _do() -> list[int]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id FROM memory WHERE embedding_state='pending' ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [int(r[0]) for r in rows]

    return await run_in_thread(_do)


async def write_embedding(memory_id: int, blob: bytes) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE memory SET embedding=?, embedding_state='ready' WHERE id=?",
                (blob, memory_id),
            )

    await run_in_thread(_do)


async def mark_failed(memory_id: int) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE memory SET embedding_state='failed' WHERE id=?",
                (memory_id,),
            )

    await run_in_thread(_do)


async def get_content(memory_id: int) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute("SELECT content FROM memory WHERE id=?", (memory_id,)).fetchone()
            return row["content"] if row else None

    return await run_in_thread(_do)


async def recall(query: str, top_k: int = 5) -> list[str]:
    """召回入口。

    - 总数 < FULL_INJECT_THRESHOLD：全量返回（按时间倒序）。
    - 否则：向量优先；Embedding 服务不可用 → 关键词 LIKE 兜底。
    """
    settings = get_settings()
    total = await count_memories()
    if total == 0:
        return []
    identity_rows = await _list_identity_memories(limit=20)
    identity_texts = [r["content"] for r in identity_rows]
    if total < settings.full_inject_threshold:
        rows = await list_memories(limit=total)
        # identity 固定前置，再补 experience，避免重复
        out: list[str] = []
        seen: set[str] = set()
        for t in identity_texts + [r["content"] for r in rows]:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    try:
        q_blob = await embed_text(query)
    except EmbeddingUnavailable:
        return await _keyword_recall(query, top_k)

    def _do() -> list[str]:
        with conn_scope(load_vec=True) as c:
            rows = c.execute(
                """
                SELECT content, vec_distance_cosine(embedding, ?) AS score
                FROM memory
                WHERE embedding_state = 'ready'
                ORDER BY score ASC
                LIMIT ?
                """,
                (q_blob, top_k),
            ).fetchall()
            return [r["content"] for r in rows]

    try:
        vec_texts = await run_in_thread(_do)
        out: list[str] = []
        seen: set[str] = set()
        for t in identity_texts + vec_texts:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out
    except Exception as exc:
        log.warning("vector_recall_failed", error=str(exc))
        kw = await _keyword_recall(query, top_k)
        out: list[str] = []
        seen: set[str] = set()
        for t in identity_texts + kw:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out


async def _keyword_recall(query: str, top_k: int) -> list[str]:
    like = f"%{query}%"

    def _do() -> list[str]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT content FROM memory WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (like, top_k),
            ).fetchall()
            return [r["content"] for r in rows]

    return await run_in_thread(_do)


async def _list_identity_memories(limit: int = 20) -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, content, anchor FROM memory WHERE anchor='identity' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


# 向量比较辅助：把 blob 反序列化为 list[float]
def _unpack_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
