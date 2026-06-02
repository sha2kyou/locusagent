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
        await enqueue_embedding(mid, bump=True)
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
        await enqueue_embedding(mid, bump=True)
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
            "将可跨会话复用的信息写入长期记忆；记忆会注入后续对话，请保持简短、只记仍长期有用的内容。\n\n"
            "何时应主动保存（不必等用户开口）：\n"
            "- 用户纠正你，或说「记住」「别再这样」\n"
            "- 用户分享偏好、习惯或个人背景（称呼、角色、时区、编码风格等）\n"
            "- 你发现环境事实（系统、已装工具、项目结构）\n"
            "- 你发现仅适用于该用户工作流的约定、API 怪癖或稳定配置\n\n"
            "优先级：用户偏好与纠正 > 环境事实 > 流程性知识。\n\n"
            "不要保存：单次问答摘要（如「用户问了某算法」）、任务进度、会话结果、"
            "已完成工作日志、临时 TODO；这些用 session_recall 从历史对话检索。\n"
            "可复用的做法应沉淀为 skill，不要塞进 memory。\n\n"
            "target：user=用户画像，memory=你的经验笔记。"
            "动作：add / replace / remove / read；兼容 update / delete / list / recall。"
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
