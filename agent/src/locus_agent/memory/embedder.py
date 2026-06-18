"""Embedding：桌面内嵌 fastembed 或 HTTP 降级。"""

from __future__ import annotations

import struct

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings
from ..logging import get_logger

log = get_logger("embedder")


class EmbeddingUnavailable(RuntimeError):
    """Embedding 服务不可达，调用方应降级到关键词检索。"""


def _vec_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    retry=retry_if_exception_type(httpx.HTTPError),
)
async def _http_embed(text: str) -> list[float]:
    settings = get_settings()
    url = f"{settings.embedding_base_url.rstrip('/')}/v1/embeddings"
    headers = {
        "X-Internal-Token": settings.internal_token,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=2.0, read=15.0, write=5.0, pool=5.0)) as client:
        resp = await client.post(
            url,
            headers=headers,
            json={
                "model": settings.embedding_model,
                "input": text,
                "encoding_format": "float",
            },
        )
        if resp.status_code != 200:
            raise httpx.HTTPStatusError(
                f"embedding http {resp.status_code}: {resp.text[:200]}",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        items = data.get("data")
        emb = items[0].get("embedding") if isinstance(items, list) and items else None
        if not isinstance(emb, list) or not emb:
            raise httpx.HTTPError("embedding service returned empty embedding")
        return [float(x) for x in emb]


async def _local_embed(text: str) -> list[float]:
    from agentpod_shared.local_embeddings import embed_vector

    return await embed_vector(text)


async def embed_text(text: str) -> bytes:
    """返回 packed float32 blob，可写入 sqlite-vec BLOB 列。"""
    if not text:
        raise ValueError("text is empty")
    settings = get_settings()
    try:
        if settings.embedding_base_url.strip().lower() == "local":
            vec = await _local_embed(text)
        else:
            vec = await _http_embed(text)
    except (httpx.HTTPError, EmbeddingUnavailable, RuntimeError, ValueError) as exc:
        log.warning("embedding_unavailable", error=str(exc))
        raise EmbeddingUnavailable(str(exc)) from exc
    except Exception as exc:
        log.warning("embedding_unavailable", error=str(exc))
        raise EmbeddingUnavailable(str(exc)) from exc
    return _vec_to_blob(vec)
