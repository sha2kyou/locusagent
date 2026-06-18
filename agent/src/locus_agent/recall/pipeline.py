"""Hybrid 召回流水线：RRF 合并 + 短 query LIKE 兜底。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from typing import Any

from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from .hybrid import attach_rrf_scores, rrf_merge_keys

log = get_logger("recall.pipeline")

SHORT_QUERY_MAX_LEN = 2


async def merge_hybrid_keys(
    *,
    top_k: int,
    vec_ranked: list[str],
    fts_ranked: list[str],
) -> tuple[list[str], dict[str, float]]:
    """双路排序结果 RRF 融合，返回 merged keys 与 score 映射。"""
    k = max(1, top_k)
    fetch_k = k * 2
    if vec_ranked:
        merged = rrf_merge_keys([vec_ranked[:fetch_k], fts_ranked[:fetch_k]], top_k=k)
    else:
        merged = fts_ranked[:k]
    scores = attach_rrf_scores(merged, [vec_ranked, fts_ranked])
    return merged, scores


async def run_hybrid_recall(
    *,
    top_k: int,
    vector_keys: Callable[[], Awaitable[list[str]]] | None,
    fts_keys: Callable[[], Awaitable[list[str]]],
    resolve: Callable[[list[str], dict[str, float]], Awaitable[list[Any]]],
) -> list[Any]:
    """执行 hybrid 召回；resolve 接收 (keys, rrf_scores)。"""
    k = max(1, top_k)
    fetch_k = k * 2

    fts_ranked = await fts_keys()
    vec_ranked: list[str] = []
    if vector_keys is not None:
        try:
            vec_ranked = await vector_keys()
        except Exception as exc:
            log.warning("hybrid_vector_keys_failed", error=str(exc))
            vec_ranked = []

    merged, scores = await merge_hybrid_keys(top_k=k, vec_ranked=vec_ranked, fts_ranked=fts_ranked)
    if not merged:
        return []
    return await resolve(merged, scores)


async def like_fallback_memory_ids(query: str, top_k: int) -> list[str]:
    like = f"%{query}%"

    def _do() -> list[str]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT CAST(id AS TEXT) AS id FROM memory WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (like, top_k),
            ).fetchall()
            return [str(r["id"]) for r in rows]

    return await run_in_thread(_do)


async def like_fallback_env_var_ids(query: str, top_k: int) -> list[str]:
    like = f"%{query}%"

    def _do() -> list[str]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT CAST(id AS TEXT) AS id FROM env_vars "
                "WHERE name LIKE ? OR description LIKE ? ORDER BY id DESC LIMIT ?",
                (like, like, top_k),
            ).fetchall()
            return [str(r["id"]) for r in rows]

    return await run_in_thread(_do)


async def like_fallback_artifact_ids(query: str, top_k: int) -> list[str]:
    like = f"%{query}%"

    def _do() -> list[str]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT id FROM artifacts "
                "WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (like, like, top_k),
            ).fetchall()
            return [str(r["id"]) for r in rows]

    return await run_in_thread(_do)
