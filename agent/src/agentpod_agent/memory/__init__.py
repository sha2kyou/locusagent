"""记忆模块：SQLite + sqlite-vec，异步 embedding，向量+关键词召回。"""

from .curator import maybe_curate_memories
from .embedder import EmbeddingUnavailable, embed_text
from .queue import enqueue_embedding, start_embedding_worker, stop_embedding_worker
from .store import (
    add_memory,
    count_memories,
    delete_memory,
    list_memories,
    recall,
    update_memory,
)

__all__ = [
    "EmbeddingUnavailable",
    "add_memory",
    "count_memories",
    "delete_memory",
    "embed_text",
    "enqueue_embedding",
    "list_memories",
    "maybe_curate_memories",
    "recall",
    "start_embedding_worker",
    "stop_embedding_worker",
    "update_memory",
]
