"""内嵌 ONNX 小模型（fastembed）。"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

import numpy as np
from fastembed import TextEmbedding

from .settings_store import embedding_cache_dir, get_settings_document

_model_lock = asyncio.Lock()
_EMBED_THREAD_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="locusagent-embed")


@lru_cache
def _load_model(model_name: str, cache_dir: str) -> TextEmbedding:
    return TextEmbedding(model_name=model_name, cache_dir=cache_dir)


def _current_model() -> TextEmbedding:
    doc = get_settings_document()
    return _load_model(doc.embedding.model, str(embedding_cache_dir(doc)))


def _embed_sync(text: str) -> list[float]:
    model = _current_model()
    vector = list(model.embed([text]))[0]
    if isinstance(vector, np.ndarray):
        return [float(x) for x in vector.tolist()]
    return [float(x) for x in vector]


async def embed_vector(text: str) -> list[float]:
    if not text:
        raise ValueError("text is empty")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_EMBED_THREAD_POOL, _embed_sync, text)


async def embed_openai_response(*, text: str, model: str | None = None) -> dict[str, Any]:
    doc = get_settings_document()
    model_name = model or doc.embedding.model
    vector = await embed_vector(text)
    return {
        "object": "list",
        "data": [{"object": "embedding", "index": 0, "embedding": vector}],
        "model": model_name,
        "usage": {"prompt_tokens": max(1, len(text) // 4), "total_tokens": max(1, len(text) // 4)},
    }


async def embed_openai_response_from_body(body: bytes) -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {}
    if body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            pass
    model = str(payload.get("model") or "") or None
    raw_input = payload.get("input")
    if isinstance(raw_input, list):
        text = "\n".join(str(x) for x in raw_input if str(x).strip())
    else:
        text = str(raw_input or "").strip()
    if not text:
        raise ValueError("embedding input is empty")
    data = await embed_openai_response(text=text, model=model)
    tokens = int(data.get("usage", {}).get("total_tokens") or 0)
    return data, tokens


async def warm_embedding_model() -> None:
    async with _model_lock:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_EMBED_THREAD_POOL, _embed_sync, "warmup")


def shutdown_embed_thread_pool() -> None:
    _EMBED_THREAD_POOL.shutdown(wait=False, cancel_futures=True)
