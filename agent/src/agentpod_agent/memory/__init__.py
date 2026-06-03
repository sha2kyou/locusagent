"""记忆模块：SQLite + sqlite-vec，异步 embedding，RAG + FTS hybrid 召回。"""

from .curator import maybe_curate_memories
from .embedder import EmbeddingUnavailable, embed_text
from .queue import (
    bump_message_embedding,
    enqueue_artifact_embedding,
    enqueue_embedding,
    enqueue_env_var_embedding,
    enqueue_message_embedding,
    start_embedding_worker,
    stop_embedding_worker,
)
from .store import (
    add_memory,
    count_memories,
    delete_memory,
    list_memories,
    recall,
    recall_items,
    update_memory,
)

__all__ = [
    "EmbeddingUnavailable",
    "add_memory",
    "count_memories",
    "delete_memory",
    "embed_text",
    "bump_message_embedding",
    "enqueue_artifact_embedding",
    "enqueue_embedding",
    "enqueue_env_var_embedding",
    "enqueue_message_embedding",
    "list_memories",
    "maybe_curate_memories",
    "recall",
    "recall_items",
    "start_embedding_worker",
    "stop_embedding_worker",
    "update_memory",
]
