"""Skill 分块向量索引与语义召回。"""

from __future__ import annotations

import hashlib
import math
import threading
from dataclasses import dataclass

from ..config import get_settings
from ..db import conn_scope, run_in_thread
from ..logging import get_logger
from ..memory.embedder import EmbeddingUnavailable, blob_to_vec, embed_text
from ..tool_settings import is_skill_enabled
from .chunking import chunk_skill
from .loader import Skill, load_all_skills

log = get_logger("skill_embeddings")

_pending_lock = threading.Lock()
_pending_skill_names: set[str] = set()
_pending_full_reindex = False


@dataclass(frozen=True, slots=True)
class SkillMatch:
    skill_name: str
    score: float
    chunk_id: str


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    similarity = dot / (na * nb)
    return max(0.0, min(1.0, 1.0 - similarity))


def _delete_skill_rows(skill_name: str) -> None:
    with conn_scope(load_vec=False) as c:
        c.execute("DELETE FROM skill_embeddings WHERE skill_name = ?", (skill_name,))


def delete_skill_embeddings(skill_name: str) -> None:
    _delete_skill_rows(skill_name)


def _purge_orphan_skill_embeddings(valid_names: set[str]) -> None:
    with conn_scope(load_vec=False) as c:
        if valid_names:
            placeholders = ",".join("?" for _ in valid_names)
            c.execute(
                f"DELETE FROM skill_embeddings WHERE skill_name NOT IN ({placeholders})",
                tuple(valid_names),
            )
        else:
            c.execute("DELETE FROM skill_embeddings")


def _fetch_ready_rows() -> list[dict]:
    with conn_scope(load_vec=False) as c:
        rows = c.execute(
            """
            SELECT skill_name, chunk_id, embedding
            FROM skill_embeddings
            WHERE embedding_state = 'ready' AND embedding IS NOT NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _upsert_chunk(skill_name: str, chunk_id: str, chunk_text: str, content_hash: str) -> bool:
    """Insert or mark pending when content changed. Returns True if embed needed."""
    with conn_scope(load_vec=False) as c:
        row = c.execute(
            """
            SELECT content_hash, embedding_state
            FROM skill_embeddings
            WHERE skill_name = ? AND chunk_id = ?
            """,
            (skill_name, chunk_id),
        ).fetchone()
        if row and row["content_hash"] == content_hash and row["embedding_state"] == "ready":
            return False
        c.execute(
            """
            INSERT INTO skill_embeddings(skill_name, chunk_id, chunk_text, content_hash, embedding, embedding_state)
            VALUES (?, ?, ?, ?, NULL, 'pending')
            ON CONFLICT(skill_name, chunk_id) DO UPDATE SET
                chunk_text = excluded.chunk_text,
                content_hash = excluded.content_hash,
                embedding = NULL,
                embedding_state = 'pending',
                updated_at = datetime('now')
            """,
            (skill_name, chunk_id, chunk_text, content_hash),
        )
    return True


def _remove_stale_chunks(skill_name: str, keep_ids: set[str]) -> None:
    with conn_scope(load_vec=False) as c:
        rows = c.execute(
            "SELECT chunk_id FROM skill_embeddings WHERE skill_name = ?",
            (skill_name,),
        ).fetchall()
        for row in rows:
            chunk_id = str(row["chunk_id"])
            if chunk_id not in keep_ids:
                c.execute(
                    "DELETE FROM skill_embeddings WHERE skill_name = ? AND chunk_id = ?",
                    (skill_name, chunk_id),
                )


def _fetch_pending_chunks(skill_name: str | None = None) -> list[dict]:
    with conn_scope(load_vec=False) as c:
        if skill_name:
            rows = c.execute(
                """
                SELECT skill_name, chunk_id, chunk_text
                FROM skill_embeddings
                WHERE embedding_state = 'pending' AND skill_name = ?
                ORDER BY skill_name, chunk_id
                """,
                (skill_name,),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT skill_name, chunk_id, chunk_text
                FROM skill_embeddings
                WHERE embedding_state = 'pending'
                ORDER BY skill_name, chunk_id
                """
            ).fetchall()
    return [dict(r) for r in rows]


def _write_chunk_embedding(skill_name: str, chunk_id: str, blob: bytes) -> None:
    with conn_scope(load_vec=False) as c:
        c.execute(
            """
            UPDATE skill_embeddings
            SET embedding = ?, embedding_state = 'ready', updated_at = datetime('now')
            WHERE skill_name = ? AND chunk_id = ?
            """,
            (blob, skill_name, chunk_id),
        )


def _mark_chunk_failed(skill_name: str, chunk_id: str) -> None:
    with conn_scope(load_vec=False) as c:
        c.execute(
            """
            UPDATE skill_embeddings
            SET embedding_state = 'failed', updated_at = datetime('now')
            WHERE skill_name = ? AND chunk_id = ?
            """,
            (skill_name, chunk_id),
        )


async def _embed_pending_chunks(skill_name: str | None = None) -> None:
    pending = await run_in_thread(_fetch_pending_chunks, skill_name)
    for row in pending:
        name = str(row["skill_name"])
        chunk_id = str(row["chunk_id"])
        text = str(row["chunk_text"] or "")
        if not text:
            await run_in_thread(_mark_chunk_failed, name, chunk_id)
            continue
        try:
            blob = await embed_text(text)
        except EmbeddingUnavailable as exc:
            log.warning("skill_chunk_embed_failed", skill=name, chunk_id=chunk_id, error=str(exc))
            await run_in_thread(_mark_chunk_failed, name, chunk_id)
            continue
        await run_in_thread(_write_chunk_embedding, name, chunk_id, blob)


def sync_skill_index(skill: Skill) -> None:
    if not is_skill_enabled(skill.name):
        _delete_skill_rows(skill.name)
        return
    chunks = chunk_skill(skill)
    keep_ids = {chunk_id for chunk_id, _ in chunks}
    _remove_stale_chunks(skill.name, keep_ids)
    for chunk_id, chunk_text in chunks:
        _upsert_chunk(skill.name, chunk_id, chunk_text, _content_hash(chunk_text))


def _get_skill(name: str) -> Skill | None:
    for skill in load_all_skills():
        if skill.name == name:
            return skill
    return None


async def reindex_skill(skill_name: str) -> None:
    skill = await run_in_thread(_get_skill, skill_name)
    if skill is None or not is_skill_enabled(skill_name):
        await run_in_thread(_delete_skill_rows, skill_name)
        return
    await run_in_thread(sync_skill_index, skill)
    await _embed_pending_chunks(skill_name)


async def reindex_all_skills() -> None:
    skills = await run_in_thread(load_all_skills)
    enabled = {s.name for s in skills if is_skill_enabled(s.name)}
    await run_in_thread(_purge_orphan_skill_embeddings, enabled)
    for skill in skills:
        if skill.name in enabled:
            await run_in_thread(sync_skill_index, skill)
        else:
            await run_in_thread(_delete_skill_rows, skill.name)
    await _embed_pending_chunks(None)
    log.info("skill_embeddings_reindexed", enabled=len(enabled))


def get_skill_reindex_pending() -> dict[str, int | bool]:
    with _pending_lock:
        return {
            "pending_skills": len(_pending_skill_names),
            "full_reindex": _pending_full_reindex,
        }


def mark_skill_reindex(skill_name: str) -> None:
    name = (skill_name or "").strip()
    if not name:
        return
    with _pending_lock:
        _pending_skill_names.add(name)


def mark_all_skills_reindex() -> None:
    global _pending_full_reindex
    with _pending_lock:
        _pending_full_reindex = True


async def flush_pending_skill_reindexes() -> None:
    global _pending_full_reindex
    with _pending_lock:
        names = set(_pending_skill_names)
        full = _pending_full_reindex
        _pending_skill_names.clear()
        _pending_full_reindex = False
    if full:
        await reindex_all_skills()
        return
    for name in sorted(names):
        await reindex_skill(name)


def schedule_skill_reindex(skill_name: str) -> None:
    mark_skill_reindex(skill_name)


def schedule_all_skills_reindex() -> None:
    mark_all_skills_reindex()


async def match_skills(query: str, *, top_k: int = 1) -> list[SkillMatch]:
    text = (query or "").strip()
    if not text:
        return []
    try:
        q_blob = await embed_text(text)
    except EmbeddingUnavailable:
        return []

    q_vec = blob_to_vec(q_blob)
    rows = await run_in_thread(_fetch_ready_rows)
    if not rows:
        return []

    best_by_skill: dict[str, SkillMatch] = {}
    max_distance = get_settings().recall_max_distance
    for row in rows:
        skill_name = str(row["skill_name"])
        if not is_skill_enabled(skill_name):
            continue
        blob = row.get("embedding")
        if not blob:
            continue
        score = _cosine_distance(q_vec, blob_to_vec(blob))
        if score > max_distance:
            continue
        chunk_id = str(row["chunk_id"])
        prev = best_by_skill.get(skill_name)
        if prev is None or score < prev.score:
            best_by_skill[skill_name] = SkillMatch(skill_name=skill_name, score=score, chunk_id=chunk_id)

    ranked = sorted(best_by_skill.values(), key=lambda m: m.score)
    k = max(1, top_k)
    return ranked[:k]
