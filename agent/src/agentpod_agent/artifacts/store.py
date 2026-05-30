"""产物与类目持久化（SQLite，单 writer 通过 asyncio.to_thread 串行）。"""

from __future__ import annotations

import secrets
from typing import Any

from ..config import get_settings
from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from ..memory.embedder import EmbeddingUnavailable, embed_text
from ..recall import fts_search
from ..recall.pipeline import (
    SHORT_QUERY_MAX_LEN,
    like_fallback_artifact_ids,
    run_hybrid_recall,
)
from ..recall.messages import truncate_embed_text

log = get_logger("artifacts")

_ARTIFACT_EMBED_CONTENT_MAX = 500


def _artifact_embed_text(title: str, content: str) -> str:
    t = str(title or "").strip()
    body = truncate_embed_text(str(content or ""), max_chars=_ARTIFACT_EMBED_CONTENT_MAX)
    if t and body:
        return f"{t}\n{body}"
    return t or body


async def fetch_pending_artifact_ids(limit: int = 50) -> list[str]:
    def _do() -> list[str]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id FROM artifacts WHERE embedding_state='pending' ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [str(r["id"]) for r in rows]

    return await run_in_thread(_do)


async def get_artifact_embed_text(artifact_id: str) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT title, content FROM artifacts WHERE id=?",
                (artifact_id,),
            ).fetchone()
            if not row:
                return None
            text = _artifact_embed_text(str(row["title"]), str(row.get("content") or ""))
            return text or None

    return await run_in_thread(_do)


async def write_artifact_embedding(artifact_id: str, blob: bytes) -> None:
    await _set_embedding(artifact_id, blob, "ready")


async def mark_artifact_embedding_failed(artifact_id: str) -> None:
    await _set_embedding(artifact_id, None, "failed")


def _new_artifact_id() -> str:
    return f"art_{secrets.token_urlsafe(12)}"


def _new_category_id() -> str:
    return f"cat_{secrets.token_urlsafe(8)}"


async def list_categories() -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, name, description, created_at FROM artifact_categories ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def create_category(name: str, description: str = "") -> dict[str, Any]:
    cid = _new_category_id()
    desc = str(description or "").strip()

    def _do() -> dict[str, Any]:
        with conn_scope(load_vec=False) as c:
            # 幂等且并发安全：同名已存在则忽略，统一按名回查
            c.execute(
                "INSERT OR IGNORE INTO artifact_categories(id, name, description) VALUES (?, ?, ?)",
                (cid, name, desc),
            )
            row = c.execute(
                "SELECT id, name, description, created_at FROM artifact_categories WHERE name = ?",
                (name,),
            ).fetchone()
            return dict(row)

    return await run_in_thread(_do)


async def update_category(
    category_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            updates = []
            params: list[Any] = []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if not updates:
                return False
            params.append(category_id)
            cur = c.execute(
                f"UPDATE artifact_categories SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            return (cur.rowcount or 0) > 0

    return await run_in_thread(_do)


async def delete_category(category_id: str) -> bool:
    """删除类目；该类目下产物降级为未分类（category_id 置 NULL）。"""

    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE artifacts SET category_id = NULL, updated_at = datetime('now') "
                "WHERE category_id = ?",
                (category_id,),
            )
            cur = c.execute(
                "DELETE FROM artifact_categories WHERE id = ?",
                (category_id,),
            )
            return (cur.rowcount or 0) > 0

    return await run_in_thread(_do)


_ALLOWED_TYPES = {"html", "markdown", "text"}


def _normalize_type(value: str | None) -> str:
    t = str(value or "").strip().lower()
    return t if t in _ALLOWED_TYPES else "markdown"


async def list_artifacts(category_id: str | None = None) -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            if category_id:
                rows = c.execute(
                    "SELECT id, category_id, type, title, content, created_at, updated_at "
                    "FROM artifacts WHERE category_id = ? ORDER BY created_at DESC",
                    (category_id,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, category_id, type, title, content, created_at, updated_at "
                    "FROM artifacts ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def get_artifact(artifact_id: str) -> dict[str, Any] | None:
    def _do() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id, category_id, type, title, content, created_at, updated_at "
                "FROM artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
            return dict(row) if row else None

    return await run_in_thread(_do)


async def create_artifact(
    *,
    title: str,
    content: str,
    type: str = "markdown",
    category_id: str | None = None,
) -> dict[str, Any]:
    aid = _new_artifact_id()
    art_type = _normalize_type(type)

    def _do() -> dict[str, Any]:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO artifacts(id, category_id, type, title, content, embedding, embedding_state) "
                "VALUES (?, ?, ?, ?, ?, NULL, 'pending')",
                (aid, category_id, art_type, title, content),
            )
            row = c.execute(
                "SELECT id, category_id, type, title, content, created_at, updated_at "
                "FROM artifacts WHERE id = ?",
                (aid,),
            ).fetchone()
            return dict(row)

    art = await run_in_thread(_do)
    from ..memory.queue import enqueue_artifact_embedding

    await enqueue_artifact_embedding(aid)

    try:
        from ..host_notify import notify_artifact_saved

        await notify_artifact_saved(art)
    except Exception as exc:
        log.warning("artifact_notify_failed", artifact_id=aid, error=str(exc))

    return art


async def update_artifact(
    artifact_id: str,
    *,
    title: str | None = None,
    content: str | None = None,
    category_id: str | None = None,
    clear_category: bool = False,
) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            updates = ["updated_at = datetime('now')"]
            params: list[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if content is not None:
                updates.append("content = ?")
                params.append(content)
            if title is not None or content is not None:
                updates.append("embedding = NULL")
                updates.append("embedding_state = 'pending'")
            if clear_category:
                updates.append("category_id = NULL")
            elif category_id is not None:
                updates.append("category_id = ?")
                params.append(category_id)
            if len(updates) == 1:
                return False
            params.append(artifact_id)
            cur = c.execute(
                f"UPDATE artifacts SET {', '.join(updates)} WHERE id = ?", params
            )
            return (cur.rowcount or 0) > 0

    need_reembed = title is not None or content is not None
    ok = await run_in_thread(_do)
    if ok and need_reembed:
        from ..memory.queue import enqueue_artifact_embedding

        await enqueue_artifact_embedding(artifact_id, bump=True)
    return ok


async def delete_artifact(artifact_id: str) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            cur = c.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
            return (cur.rowcount or 0) > 0

    return await run_in_thread(_do)


async def _set_embedding(artifact_id: str, blob: bytes | None, state: str) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE artifacts SET embedding = ?, embedding_state = ? WHERE id = ?",
                (blob, state, artifact_id),
            )

    await run_in_thread(_do)


def _to_hit(row: dict[str, Any], *, score: float | None = None) -> dict[str, Any]:
    content = str(row.get("content") or "")
    flat = " ".join(content.split())
    return {
        "id": row.get("id"),
        "category_id": row.get("category_id"),
        "type": row.get("type"),
        "title": row.get("title"),
        "created_at": row.get("created_at"),
        "snippet": flat[:160] + ("…" if len(flat) > 160 else ""),
        "score": round(float(score), 4) if score is not None else None,
    }


async def recall_artifacts(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """RAG + FTS hybrid 召回产物（title + content）。"""
    if not query or not query.strip():
        return []
    k = max(1, top_k)
    fetch_k = k * 2
    max_distance = get_settings().recall_max_distance

    q_blob: bytes | None = None
    try:
        q_blob = await embed_text(query)
    except EmbeddingUnavailable:
        q_blob = None

    async def _fts_keys() -> list[str]:
        hits = await fts_search(
            fts_table="artifacts_fts",
            from_clause="FROM artifacts_fts JOIN artifacts a ON a.rowid = artifacts_fts.rowid",
            select_columns="a.id AS id",
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
                    SELECT id, vec_distance_cosine(embedding, ?) AS score
                    FROM artifacts
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
            log.warning("artifact_vector_recall_failed", error=str(exc))
            return []

    async def _resolve(keys: list[str], scores: dict[str, float]) -> list[dict[str, Any]]:
        if not keys:
            return []

        def _do() -> list[dict[str, Any]]:
            placeholders = ",".join("?" * len(keys))
            with conn_scope(load_vec=False) as c:
                rows = c.execute(
                    "SELECT id, category_id, type, title, content, created_at "
                    f"FROM artifacts WHERE id IN ({placeholders})",
                    keys,
                ).fetchall()
            by_id = {str(r["id"]): dict(r) for r in rows}
            return [
                _to_hit(by_id[key], score=scores.get(key))
                for key in keys
                if key in by_id
            ]

        return await run_in_thread(_do)

    vec_fn = _vec_keys if q_blob is not None else None
    hits = await run_hybrid_recall(
        top_k=k,
        vector_keys=vec_fn,
        fts_keys=_fts_keys,
        resolve=_resolve,
    )
    if not hits and len(query.strip()) <= SHORT_QUERY_MAX_LEN:
        like_keys = await like_fallback_artifact_ids(query, k)
        hits = await _resolve(like_keys, {})
    return hits


async def resolve_category_id(name: str) -> str | None:
    """按类目名查 id；不存在返回 None。供工具按名归档使用。"""

    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id FROM artifact_categories WHERE name = ?",
                (name,),
            ).fetchone()
            return str(row["id"]) if row else None

    return await run_in_thread(_do)


async def get_category_name(category_id: str | None) -> str | None:
    """按类目 id 查名称；不存在返回 None。"""

    if not category_id:
        return None

    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT name FROM artifact_categories WHERE id = ?",
                (category_id,),
            ).fetchone()
            return str(row["name"]) if row else None

    return await run_in_thread(_do)
