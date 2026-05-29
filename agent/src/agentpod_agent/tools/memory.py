"""memory 工具：增删改查 + 召回。"""

from __future__ import annotations

from typing import Any

from ..memory import (
    add_memory,
    delete_memory,
    enqueue_embedding,
    list_memories,
    recall,
    update_memory,
)
from ..security import review_write
from .base import Tool, ToolError, ToolResult, register_builtin


async def _memory_tool(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action", "")).lower()
    if action == "add":
        content = str(args.get("content", "")).strip()
        if not content:
            raise ToolError("content is required for add")
        verdict = await review_write(content, kind="memory")
        if not verdict.allowed:
            raise ToolError(f"memory write blocked by guard: {verdict.reason}")
        mid = await add_memory(content)
        await enqueue_embedding(mid)
        return ToolResult(content=f"memory#{mid} saved")
    if action == "update":
        mid = int(args.get("id", 0) or 0)
        content = str(args.get("content", "")).strip()
        if not mid or not content:
            raise ToolError("id and content are required for update")
        ok = await update_memory(mid, content)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        await enqueue_embedding(mid)
        return ToolResult(content=f"memory#{mid} updated")
    if action == "delete":
        mid = int(args.get("id", 0) or 0)
        if not mid:
            raise ToolError("id is required for delete")
        ok = await delete_memory(mid)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        return ToolResult(content=f"memory#{mid} deleted")
    if action == "list":
        rows = await list_memories(limit=int(args.get("limit", 50) or 50))
        if not rows:
            return ToolResult(content="(empty)")
        return ToolResult(
            content="\n".join(f"#{r['id']}[{r['embedding_state']}] {r['content']}" for r in rows),
            metadata={"items": rows},
        )
    if action == "recall":
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolError("query is required for recall")
        top_k = int(args.get("top_k", 5) or 5)
        hits = await recall(query, top_k=top_k)
        if not hits:
            return ToolResult(content="(no recall hits)")
        return ToolResult(content="\n".join(f"- {h}" for h in hits))
    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="memory",
        description="管理长期记忆：add / update / delete / list / recall。",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "update", "delete", "list", "recall"]},
                "id": {"type": "integer"},
                "content": {"type": "string"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["action"],
        },
        handler=_memory_tool,
    )
)
