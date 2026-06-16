from __future__ import annotations

from typing import Any

from sqlite3 import IntegrityError

from ..config import get_settings
from ..subprocess_env import is_reserved_env_name, normalize_env_names
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


async def fetch_pending_env_var_ids(limit: int = 50) -> list[int]:
    def _do() -> list[int]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id FROM env_vars WHERE embedding_state='pending' ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [int(r[0]) for r in rows]

    return await run_in_thread(_do)


async def env_var_embedding_state(env_id: int) -> str | None:
    def _do() -> str | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT embedding_state FROM env_vars WHERE id=?",
                (env_id,),
            ).fetchone()
            return str(row["embedding_state"]) if row else None

    return await run_in_thread(_do)


async def get_env_var_embed_text(env_id: int) -> str | None:
    def _do() -> dict[str, Any] | None:
        with conn_scope(load_vec=False) as c:
            row = c.execute(
                "SELECT id, name, description FROM env_vars WHERE id=?",
                (env_id,),
            ).fetchone()
            return dict(row) if row else None

    row = await run_in_thread(_do)
    if row is None:
        return None
    return _recall_text(str(row["name"]), str(row.get("description") or ""))


async def mark_env_var_embedding_failed(env_id: int) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE env_vars SET embedding=NULL, embedding_state='failed', "
                "updated_at=datetime('now') WHERE id=?",
                (env_id,),
            )

    await run_in_thread(_do)


async def write_env_var_embedding(env_id: int, blob: bytes) -> None:
    def _do() -> None:
        with conn_scope(load_vec=False) as c:
            c.execute(
                "UPDATE env_vars SET embedding=?, embedding_state='ready', "
                "updated_at=datetime('now') WHERE id=?",
                (blob, env_id),
            )

    await run_in_thread(_do)


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


async def get_env_vars_by_names(names: list[str]) -> dict[str, str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in names:
        n = _normalize_name(raw)
        if not n or n in seen:
            continue
        seen.add(n)
        normalized.append(n)
    if not normalized:
        return {}

    def _do() -> dict[str, str]:
        placeholders = ",".join("?" * len(normalized))
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                f"SELECT name, value FROM env_vars WHERE name IN ({placeholders})",
                normalized,
            ).fetchall()
        return {str(r["name"]): str(r["value"]) for r in rows}

    return await run_in_thread(_do)


async def resolve_env_var_names(names: list[str]) -> dict[str, str]:
    normalized = normalize_env_names(names)
    if not normalized:
        return {}
    reserved = [n for n in normalized if is_reserved_env_name(n)]
    if reserved:
        raise ValueError(f"env var name not allowed: {', '.join(reserved)}")
    resolved = await get_env_vars_by_names(normalized)
    missing = [n for n in normalized if n not in resolved]
    if missing:
        raise ValueError(f"env var not found: {', '.join(missing)}")
    return {n: resolved[n] for n in normalized}


async def add_env_var(name: str, value: str, description: str = "") -> int:
    n = _normalize_name(name)
    if not n:
        raise ValueError("name is empty")
    if is_reserved_env_name(n):
        raise ValueError(f"reserved env var name: {n}")
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
    from ..memory.queue import enqueue_env_var_embedding

    await enqueue_env_var_embedding(env_id)
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
    if has_name and is_reserved_env_name(str(name)):
        raise ValueError(f"reserved env var name: {name}")
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
            reindex = has_name or has_description
            if reindex:
                set_parts.extend(["embedding=NULL", "embedding_state='pending'"])
            set_parts.append("updated_at=datetime('now')")
            params.append(env_id)
            sql = f"UPDATE env_vars SET {', '.join(set_parts)} WHERE id=?"
            try:
                cur = c.execute(sql, params)
            except IntegrityError as exc:
                raise FileExistsError("env var already exists") from exc
            return cur.rowcount > 0, reindex

    ok, reindex = await run_in_thread(_do)
    if ok and reindex:
        from ..memory.queue import enqueue_env_var_embedding

        await enqueue_env_var_embedding(env_id, bump=True)
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


