"""FTS5 trigram 检索封装。"""

from __future__ import annotations

from typing import Any

from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from .hybrid import fts_match_quote

log = get_logger("recall.fts")


def _table_exists(c: Any, name: str) -> bool:
    row = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


async def fts_search(
    *,
    fts_table: str,
    from_clause: str,
    select_columns: str,
    query: str,
    top_k: int,
    where_extra: str = "",
    min_query_len: int = 1,
) -> list[dict[str, Any]]:
    """通用 FTS 检索；表不存在或 query 过短时返回空列表。"""
    q = str(query or "").strip()
    if not q or len(q) < min_query_len:
        return []
    match = fts_match_quote(q)
    limit = max(1, top_k)
    extra = f" AND ({where_extra})" if where_extra else ""

    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            if not _table_exists(c, fts_table):
                return []
            sql = f"""
                SELECT {select_columns}, bm25({fts_table}) AS rank
                {from_clause}
                WHERE {fts_table} MATCH ?{extra}
                ORDER BY rank
                LIMIT ?
            """
            rows = c.execute(sql, (match, limit)).fetchall()
            return [dict(r) for r in rows]

    try:
        return await run_in_thread(_do)
    except Exception as exc:
        log.warning("fts_search_failed", table=fts_table, error=str(exc))
        return []
