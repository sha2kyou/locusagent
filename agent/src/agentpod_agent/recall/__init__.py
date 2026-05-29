"""统一召回：RAG（向量）+ FTS hybrid。"""

from .fts import fts_search
from .hybrid import attach_rrf_scores, fts_match_quote, hybrid_recall_by_key, rrf_merge_keys
from .pipeline import (
    SHORT_QUERY_MAX_LEN,
    like_fallback_artifact_ids,
    like_fallback_env_var_ids,
    like_fallback_memory_ids,
    merge_hybrid_keys,
    run_hybrid_recall,
)

__all__ = [
    "SHORT_QUERY_MAX_LEN",
    "attach_rrf_scores",
    "fts_match_quote",
    "fts_search",
    "hybrid_recall_by_key",
    "like_fallback_artifact_ids",
    "like_fallback_env_var_ids",
    "like_fallback_memory_ids",
    "merge_hybrid_keys",
    "rrf_merge_keys",
    "run_hybrid_recall",
]
