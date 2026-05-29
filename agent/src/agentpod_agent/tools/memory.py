"""memory 工具：长期记忆增删改查 + 召回。"""

from __future__ import annotations

from typing import Any

from ..memory import add_memory, delete_memory, enqueue_embedding, list_memories, recall, update_memory
from ..security import review_write
from .base import Tool, ToolError, ToolResult, register_builtin


async def _memory_tool(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action", "")).lower()
    target = str(args.get("target", "memory") or "memory").strip().lower()
    if target not in {"memory", "user"}:
        raise ToolError("target must be one of: memory, user")
    anchor = "identity" if target == "user" else "experience"

    async def _select_by_old_text(old_text: str) -> int:
        rows = await list_memories(limit=500)
        scoped = [r for r in rows if str(r.get("anchor") or "experience") == anchor]
        matches = [r for r in scoped if old_text in str(r.get("content") or "")]
        if not matches:
            raise ToolError(f"No entry matched '{old_text}'.")
        if len(matches) > 1:
            unique_texts = {str(r.get("content") or "") for r in matches}
            if len(unique_texts) > 1:
                previews = [str(r.get("content") or "")[:80] for r in matches[:5]]
                raise ToolError(
                    f"Multiple entries matched '{old_text}'. Be more specific. matches={previews}"
                )
        return int(matches[0]["id"])

    if action == "add":
        content = str(args.get("content", "")).strip()
        if not content:
            raise ToolError("content is required for add")
        verdict = await review_write(content, kind="memory")
        if not verdict.allowed:
            raise ToolError(f"memory write blocked by guard: {verdict.reason}")
        mid = await add_memory(content, anchor=anchor)
        await enqueue_embedding(mid)
        return ToolResult(content=f"memory#{mid} saved")

    if action == "replace":
        old_text = str(args.get("old_text", "")).strip()
        content = str(args.get("content", "")).strip()
        if not old_text:
            raise ToolError("old_text is required for replace")
        if not content:
            raise ToolError("content is required for replace")
        verdict = await review_write(content, kind="memory")
        if not verdict.allowed:
            raise ToolError(f"memory write blocked by guard: {verdict.reason}")
        mid = await _select_by_old_text(old_text)
        ok = await update_memory(mid, content, anchor=anchor)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        await enqueue_embedding(mid)
        return ToolResult(content=f"memory#{mid} replaced")

    if action == "remove":
        old_text = str(args.get("old_text", "")).strip()
        if not old_text:
            raise ToolError("old_text is required for remove")
        mid = await _select_by_old_text(old_text)
        ok = await delete_memory(mid)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        return ToolResult(content=f"memory#{mid} removed")

    if action == "read":
        rows = await list_memories(limit=int(args.get("limit", 100) or 100))
        scoped = [r for r in rows if str(r.get("anchor") or "experience") == anchor]
        if not scoped:
            return ToolResult(content="(empty)")
        return ToolResult(content="\n".join(f"- {r['content']}" for r in scoped), metadata={"items": scoped})

    # 兼容旧动作
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
        description=(
            "管理长期记忆。推荐动作：add / replace / remove / read，"
            "并通过 target 区分 user（用户画像）与 memory（经验笔记）。"
            "兼容旧动作：update / delete / list / recall。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "add",
                        "replace",
                        "remove",
                        "read",
                        "update",
                        "delete",
                        "list",
                        "recall",
                    ],
                },
                "target": {"type": "string", "enum": ["memory", "user"], "default": "memory"},
                "id": {"type": "integer"},
                "content": {"type": "string"},
                "old_text": {"type": "string"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["action"],
        },
        handler=_memory_tool,
    )
)
