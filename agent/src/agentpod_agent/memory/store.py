"""记忆 CRUD + 召回。

约束：
- 写入时不阻塞：仅入库 content + state=pending，由 embedding worker 异步生成向量。
- 召回：少于 N 条全量注入；否则 RAG + FTS hybrid（RRF 融合）。
"""

from __future__ import annotations

import struct
from typing import Any

from ..config import get_settings
from ..core.write_origin import ORIGIN_AUTO_EXTRACT, ORIGIN_MANUAL
from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from ..recall import fts_search
from ..recall.pipeline import (
    SHORT_QUERY_MAX_LEN,
    like_fallback_memory_ids,
    run_hybrid_recall,
)
from .embedder import EmbeddingUnavailable, embed_text

log = get_logger("memory")

MEMORY_ANCHOR_LONG = "identity"
MEMORY_ANCHOR_SHORT = "experience"

_ANCHOR_ALIASES_LONG = frozenset(
    {"identity", "user", "long_term", "long", "longterm", "长期", "长期记忆"}
)
_ANCHOR_ALIASES_SHORT = frozenset(
    {"experience", "memory", "short_term", "short", "shortterm", "短期", "短期记忆"}
)


def resolve_memory_anchor_input(value: str | None, *, default: str = MEMORY_ANCHOR_SHORT) -> str:
    """将 term/target/anchor 别名解析为 identity（长期）或 experience（短期）。"""
    raw = str(value or "").strip().lower()
    if not raw:
        return _normalize_anchor(default)
    if raw in _ANCHOR_ALIASES_LONG:
        return MEMORY_ANCHOR_LONG
    if raw in _ANCHOR_ALIASES_SHORT:
        return MEMORY_ANCHOR_SHORT
    raise ValueError(
        "term must be long_term or short_term "
        "(aliases: user/memory, identity/experience)"
    )


def memory_term_label(anchor: str | None) -> str:
    raw = str(anchor or "").strip().lower()
    if raw in _ANCHOR_ALIASES_LONG:
        return "长期"
    if raw in _ANCHOR_ALIASES_SHORT or not raw:
        return "短期"
    return "长期" if _normalize_anchor(anchor) == MEMORY_ANCHOR_LONG else "短期"


def _normalize_anchor(anchor: str | None) -> str:
    a = str(anchor or "experience").strip().lower()
    return a if a in {"identity", "experience"} else "experience"


def _normalize_origin(origin: str | None) -> str:
    o = str(origin or ORIGIN_MANUAL).strip().lower()
    return o if o in {ORIGIN_MANUAL, ORIGIN_AUTO_EXTRACT} else ORIGIN_MANUAL


async def add_memory(content: str, *, anchor: str = "experience", origin: str = ORIGIN_MANUAL) -> int:
    if not content or not content.strip():
        raise ValueError("content is empty")
    a = _normalize_anchor(anchor)
    o = _normalize_origin(origin)

    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            cur = c.execute(
                "INSERT INTO memory(content, anchor, origin) VALUES(?, ?, ?)",
                (content, a, o),
            )
            return int(cur.lastrowid or 0)

    return await run_in_thread(_do)


async def update_memory(
    memory_id: int,
    content: str | None = None,
    *,
    anchor: str | None = None,
    origin: str | None = None,
) -> bool:
    has_content = content is not None
    has_anchor = anchor is not None
    has_origin = origin is not None
    if not has_content and not has_anchor and not has_origin:
        raise ValueError("nothing to update")
    if has_content and not str(content).strip():
        raise ValueError("content is empty")
    normalized_anchor = _normalize_anchor(anchor) if has_anchor else None
    normalized_origin = _normalize_origin(origin) if has_origin else None

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
            if has_origin:
                set_parts.append("origin=?")
                params.append(str(normalized_origin))
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
                "SELECT id, content, anchor, origin, embedding_state, created_at "
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


async def memory_embedding_state(memory_id: int) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT embedding_state FROM memory WHERE id=?",
                (memory_id,),
            ).fetchone()
            return str(row["embedding_state"]) if row else None

    return await run_in_thread(_do)


async def get_content(memory_id: int) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute("SELECT content FROM memory WHERE id=?", (memory_id,)).fetchone()
            return row["content"] if row else None

    return await run_in_thread(_do)


async def recall_items(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """召回记忆条目（含 id / content / anchor）。"""
    settings = get_settings()
    total = await count_memories()
    if total == 0:
        return []
    identity_rows = await _list_identity_memories(limit=20)
    if total < settings.full_inject_threshold:
        rows = await list_memories(limit=total)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in identity_rows + rows:
            text = str(row.get("content") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(
                {
                    "id": int(row["id"]),
                    "content": text,
                    "anchor": str(row.get("anchor") or "experience"),
                }
            )
        return out

    k = max(1, top_k)
    fetch_k = k * 2
    q_blob: bytes | None = None
    try:
        q_blob = await embed_text(query)
    except EmbeddingUnavailable:
        q_blob = None

    max_distance = settings.recall_max_distance

    async def _fts_keys() -> list[str]:
        hits = await fts_search(
            fts_table="memory_fts",
            from_clause="FROM memory_fts JOIN memory m ON m.id = memory_fts.rowid",
            select_columns="CAST(m.id AS TEXT) AS id",
            query=query,
            top_k=fetch_k,
        )
        return [str(h["id"]) for h in hits]

    async def _vec_keys() -> list[str]:
        if q_blob is None:
            return []

        def _do() -> list[str]:
            with conn_scope(load_vec=True) as c:
                rows = c.execute(
                    """
                    SELECT CAST(id AS TEXT) AS id, vec_distance_cosine(embedding, ?) AS score
                    FROM memory
                    WHERE embedding_state = 'ready'
                    ORDER BY score ASC
                    LIMIT ?
                    """,
                    (q_blob, fetch_k),
                ).fetchall()
                return [
                    str(r["id"])
                    for r in rows
                    if r["score"] is not None and r["score"] <= max_distance
                ]

        try:
            return await run_in_thread(_do)
        except Exception as exc:
            log.warning("vector_recall_failed", error=str(exc))
            return []

    async def _resolve(keys: list[str], _scores: dict[str, float]) -> list[dict[str, Any]]:
        if not keys:
            return []

        def _do() -> list[dict[str, Any]]:
            placeholders = ",".join("?" * len(keys))
            with conn_scope(load_vec=False) as c:
                rows = c.execute(
                    f"SELECT id, content, anchor FROM memory WHERE id IN ({placeholders})",
                    keys,
                ).fetchall()
            by_id = {str(r["id"]): dict(r) for r in rows}
            return [by_id[key] for key in keys if key in by_id]

        return await run_in_thread(_do)

    vec_fn = _vec_keys if q_blob is not None else None
    recalled = await run_hybrid_recall(
        top_k=k,
        vector_keys=vec_fn,
        fts_keys=_fts_keys,
        resolve=_resolve,
    )
    if not recalled and len(query.strip()) <= SHORT_QUERY_MAX_LEN:
        like_keys = await like_fallback_memory_ids(query, k)
        recalled = await _resolve(like_keys, {})

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in identity_rows + recalled:
        text = str(row.get("content") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(
            {
                "id": int(row["id"]),
                "content": text,
                "anchor": str(row.get("anchor") or "experience"),
            }
        )
    return out


async def recall(query: str, top_k: int = 5) -> list[str]:
    """召回入口（仅正文，兼容旧调用方）。"""
    items = await recall_items(query, top_k=top_k)
    return [str(r["content"]) for r in items]


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
