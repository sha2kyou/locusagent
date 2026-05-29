from __future__ import annotations

from typing import Any

from sqlite3 import IntegrityError

from ..config import get_settings
from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from ..memory.embedder import EmbeddingUnavailable, embed_text
from ..recall import fts_search
from ..recall.pipeline import (
    SHORT_QUERY_MAX_LEN,
    like_fallback_env_var_ids,
    run_hybrid_recall,
)

log = get_logger("env_vars")


def _normalize_name(name: str) -> str:
    return str(name or "").strip()


def _recall_text(name: str, description: str) -> str:
    n = _normalize_name(name)
    d = str(description or "").strip()
    if d:
        return f"{n}\n{d}"
    return n


async def list_env_vars(limit: int = 200) -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id, name, value, description, embedding_state, created_at, updated_at "
                "FROM env_vars ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await run_in_thread(_do)


async def add_env_var(name: str, value: str, description: str = "") -> int:
    n = _normalize_name(name)
    if not n:
        raise ValueError("name is empty")
    if not str(value).strip():
        raise ValueError("value is empty")

    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            try:
                cur = c.execute(
                    "INSERT INTO env_vars(name, value, description) VALUES(?, ?, ?)",
                    (n, str(value), str(description or "")),
                )
            except IntegrityError as exc:
                raise FileExistsError("env var already exists") from exc
            return int(cur.lastrowid or 0)

    env_id = await run_in_thread(_do)
    await _refresh_embedding(env_id)
    return env_id


async def update_env_var(
    env_id: int,
    *,
    name: str | None = None,
    value: str | None = None,
    description: str | None = None,
) -> bool:
    has_name = name is not None
    has_value = value is not None
    has_description = description is not None
    if not has_name and not has_value and not has_description:
        raise ValueError("nothing to update")
    if has_name and not _normalize_name(str(name)):
        raise ValueError("name is empty")
    if has_value and not str(value).strip():
        raise ValueError("value is empty")

    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            set_parts: list[str] = []
            params: list[Any] = []
            if has_name:
                set_parts.append("name=?")
                params.append(_normalize_name(str(name)))
            if has_value:
                set_parts.append("value=?")
                params.append(str(value))
            if has_description:
                set_parts.append("description=?")
                params.append(str(description or ""))
            set_parts.extend(["embedding=NULL", "embedding_state='pending'", "updated_at=datetime('now')"])
            params.append(env_id)
            sql = f"UPDATE env_vars SET {', '.join(set_parts)} WHERE id=?"
            try:
                cur = c.execute(sql, params)
            except IntegrityError as exc:
                raise FileExistsError("env var already exists") from exc
            return cur.rowcount > 0

    ok = await run_in_thread(_do)
    if ok:
        await _refresh_embedding(env_id)
    return ok


async def delete_env_var(env_id: int) -> bool:
    def _do() -> bool:
        with conn_scope(load_vec=False) as c:
            cur = c.execute("DELETE FROM env_vars WHERE id=?", (env_id,))
            return cur.rowcount > 0

    return await run_in_thread(_do)


async def recall_env_vars(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    k = max(1, min(int(top_k or 5), 20))
    fetch_k = k * 2
    max_distance = get_settings().recall_max_distance

    q_blob: bytes | None = None
    try:
        q_blob = await embed_text(q)
    except EmbeddingUnavailable:
        q_blob = None

    async def _fts_keys() -> list[str]:
        hits = await fts_search(
            fts_table="env_vars_fts",
            from_clause="FROM env_vars_fts JOIN env_vars e ON e.id = env_vars_fts.rowid",
            select_columns="CAST(e.id AS TEXT) AS id",
            query=q,
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
                    FROM env_vars
                    WHERE embedding_state='ready'
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
            log.warning("env_var_vector_recall_failed", error=str(exc))
            return []

    async def _resolve(keys: list[str], _scores: dict[str, float]) -> list[dict[str, Any]]:
        if not keys:
            return []

        def _do() -> list[dict[str, Any]]:
            placeholders = ",".join("?" * len(keys))
            with conn_scope(load_vec=False) as c:
                rows = c.execute(
                    "SELECT id, name, value, description, embedding_state, created_at, updated_at "
                    f"FROM env_vars WHERE id IN ({placeholders})",
                    keys,
                ).fetchall()
            by_id = {str(r["id"]): dict(r) for r in rows}
            return [by_id[key] for key in keys if key in by_id]

        return await run_in_thread(_do)

    vec_fn = _vec_keys if q_blob is not None else None
    hits = await run_hybrid_recall(
        top_k=k,
        vector_keys=vec_fn,
        fts_keys=_fts_keys,
        resolve=_resolve,
    )
    if not hits and len(q) <= SHORT_QUERY_MAX_LEN:
        like_keys = await like_fallback_env_var_ids(q, k)
        hits = await _resolve(like_keys, {})
    return hits


async def _refresh_embedding(env_id: int) -> None:
    def _load() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id, name, description FROM env_vars WHERE id=?",
                (env_id,),
            ).fetchone()
            return dict(row) if row else None

    row = await run_in_thread(_load)
    if not row:
        return
    text = _recall_text(str(row["name"]), str(row.get("description") or ""))
    try:
        emb = await embed_text(text)
    except EmbeddingUnavailable:
        return
    except Exception:
        def _mark_failed() -> None:
            with conn_scope(load_vec=False) as c:
                c.execute(
                    "UPDATE env_vars SET embedding=NULL, embedding_state='failed', updated_at=datetime('now') WHERE id=?",
                    (env_id,),
                )

        await run_in_thread(_mark_failed)
        return

    def _write() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE env_vars SET embedding=?, embedding_state='ready', updated_at=datetime('now') WHERE id=?",
                (emb, env_id),
            )

    await run_in_thread(_write)
