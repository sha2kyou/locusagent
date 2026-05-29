"""Hybrid recall：向量 + FTS 双路召回，RRF 融合。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from ..logging import get_logger

log = get_logger("recall.hybrid")

T = TypeVar("T")

RRF_K = 60


def fts_match_quote(query: str) -> str:
    """将 query 包装为 FTS5 短语匹配。"""
    return '"' + str(query or "").replace('"', '""') + '"'


def rrf_merge_keys(ranked_lists: Sequence[Sequence[str]], *, top_k: int, k: int = RRF_K) -> list[str]:
    """Reciprocal Rank Fusion：按 key 合并多路排序结果。"""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked):
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    ordered = sorted(scores.keys(), key=lambda item: scores[item], reverse=True)
    return ordered[: max(1, top_k)]


async def hybrid_recall_by_key(
    *,
    top_k: int,
    vector_keys: Callable[[], Awaitable[list[str]]] | None,
    fts_keys: Callable[[], Awaitable[list[str]]],
    resolve: Callable[[list[str]], Awaitable[list[T]]],
) -> list[T]:
    """双路召回 + RRF；vector 不可用时仅走 FTS。"""
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

    if vec_ranked:
        merged_keys = rrf_merge_keys([vec_ranked[:fetch_k], fts_ranked[:fetch_k]], top_k=k)
    else:
        merged_keys = fts_ranked[:k]

    if not merged_keys:
        return []
    return await resolve(merged_keys)


def attach_rrf_scores(keys: list[str], ranked_lists: Sequence[Sequence[str]], *, k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked):
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    return {key: round(scores.get(key, 0.0), 4) for key in keys}
