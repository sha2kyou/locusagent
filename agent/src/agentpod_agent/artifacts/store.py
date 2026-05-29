"""产物与类目持久化（SQLite，单 writer 通过 asyncio.to_thread 串行）。"""

from __future__ import annotations

import secrets
from typing import Any

from ..config import get_settings
from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from ..memory.embedder import EmbeddingUnavailable, embed_text

log = get_logger("artifacts")


async def _embed_title(title: str) -> bytes | None:
    """对标题生成向量，失败返回 None（调用方落 pending，召回时再补/降级）。"""
    if not title or not title.strip():
        return None
    try:
        return await embed_text(title)
    except EmbeddingUnavailable:
        return None
    except Exception as exc:
        log.warning("artifact_embed_failed", error=str(exc))
        return None


def _new_artifact_id() -> str:
    return f"art_{secrets.token_urlsafe(12)}"


def _new_category_id() -> str:
    return f"cat_{secrets.token_urlsafe(8)}"


async def list_categories() -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, name, created_at FROM artifact_categories ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def create_category(name: str) -> dict[str, Any]:
    cid = _new_category_id()

    def _do() -> dict[str, Any]:
        with conn_scope(load_vec=False) as c:
            # 幂等且并发安全：同名已存在则忽略，统一按名回查
            c.execute(
                "INSERT OR IGNORE INTO artifact_categories(id, name) VALUES (?, ?)",
                (cid, name),
            )
            row = c.execute(
                "SELECT id, name, created_at FROM artifact_categories WHERE name = ?",
                (name,),
            ).fetchone()
            return dict(row)

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
    blob = await _embed_title(title)
    state = "ready" if blob is not None else "pending"

    def _do() -> dict[str, Any]:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "INSERT INTO artifacts(id, category_id, type, title, content, embedding, embedding_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (aid, category_id, art_type, title, content, blob, state),
            )
            row = c.execute(
                "SELECT id, category_id, type, title, content, created_at, updated_at "
                "FROM artifacts WHERE id = ?",
                (aid,),
            ).fetchone()
            return dict(row)

    return await run_in_thread(_do)


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
                # 标题变更：清空旧向量，召回时惰性重建
                updates.append("embedding = NULL")
                updates.append("embedding_state = 'pending'")
            if content is not None:
                updates.append("content = ?")
                params.append(content)
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

    return await run_in_thread(_do)


async def delete_artifact(artifact_id: str) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            cur = c.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
            return (cur.rowcount or 0) > 0

    return await run_in_thread(_do)


async def _embed_pending_artifacts(limit: int = 50) -> None:
    """惰性补齐未就绪的标题向量（含历史产物）；服务不可用则整轮放弃。"""

    def _fetch() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, title FROM artifacts WHERE embedding_state != 'ready' LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    pending = await run_in_thread(_fetch)
    for p in pending:
        try:
            blob = await embed_text(str(p["title"]))
        except EmbeddingUnavailable:
            break
        except Exception as exc:
            log.warning("artifact_embed_failed", id=p["id"], error=str(exc))
            await _set_embedding(str(p["id"]), None, "failed")
            continue
        await _set_embedding(str(p["id"]), blob, "ready")


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


async def _keyword_recall_artifacts(query: str, top_k: int) -> list[dict[str, Any]]:
    like = f"%{query}%"

    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, category_id, type, title, content, created_at FROM artifacts "
                "WHERE title LIKE ? ORDER BY created_at DESC LIMIT ?",
                (like, top_k),
            ).fetchall()
            return [_to_hit(dict(r)) for r in rows]

    return await run_in_thread(_do)


async def recall_artifacts(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """按标题语义召回产物；向量优先，服务不可用或无命中时回退标题关键词。"""
    if not query or not query.strip():
        return []
    await _embed_pending_artifacts()
    try:
        q_blob = await embed_text(query)
    except EmbeddingUnavailable:
        return await _keyword_recall_artifacts(query, top_k)

    max_distance = get_settings().recall_max_distance

    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=True) as c:
            rows = c.execute(
                """
                SELECT id, category_id, type, title, content, created_at,
                       vec_distance_cosine(embedding, ?) AS score
                FROM artifacts
                WHERE embedding_state = 'ready'
                ORDER BY score ASC
                LIMIT ?
                """,
                (q_blob, top_k),
            ).fetchall()
            return [
                _to_hit(dict(r), score=r["score"])
                for r in rows
                if r["score"] is not None and r["score"] <= max_distance
            ]

    try:
        hits = await run_in_thread(_do)
    except Exception as exc:
        log.warning("artifact_vector_recall_failed", error=str(exc))
        return await _keyword_recall_artifacts(query, top_k)
    return hits or await _keyword_recall_artifacts(query, top_k)


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
