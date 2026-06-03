"""memory 工具：长期记忆增删改查 + 召回。"""

from __future__ import annotations

from typing import Any

from ..core.write_origin import ORIGIN_AUTO_EXTRACT, ORIGIN_MANUAL, is_auto_extract_write
from ..memory import (
    add_memory,
    delete_memory,
    enqueue_embedding,
    list_memories,
    recall_items,
    update_memory,
)
from ..security import review_write
from .args import pick_action, pick_int, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


async def _memory_tool(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)
    if action == "delete":
        action = "remove"
    target = pick_str(args, "target") or "memory"
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

    async def _resolve_entry_id(*, for_remove: bool = False) -> int:
        mid = pick_int(args, "id", "memory_id")
        if mid:
            return mid
        match_keys: tuple[str, ...] = ("old_text", "old_string", "old_content", "match")
        if for_remove:
            match_keys = (*match_keys, "content", "text")
        old_text = pick_str(args, *match_keys)
        if not old_text:
            hint = "id or old_text is required"
            if for_remove:
                hint += " (for remove, content/text may identify the entry)"
            raise ToolError(f"{hint} (use id from snapshot/read/list/recall, or a unique substring)")
        return await _select_by_old_text(old_text)

    if action == "add":
        content = pick_str(args, "content", "text", "new_string", "new_content")
        if not content:
            raise ToolError("content is required for add")
        verdict = await review_write(content, kind="memory")
        if not verdict.allowed:
            raise ToolError(f"memory write blocked by guard: {verdict.reason}")
        mid = await add_memory(
            content,
            anchor=anchor,
            origin=ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else ORIGIN_MANUAL,
        )
        await enqueue_embedding(mid)
        saved_origin = ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else ORIGIN_MANUAL
        origin_label = " [auto_extract]" if saved_origin == ORIGIN_AUTO_EXTRACT else ""
        return ToolResult(content=f"memory#{mid} saved{origin_label}")

    if action in {"replace", "update"}:
        content = pick_str(args, "content", "new_string", "new_content", "text")
        if not content:
            raise ToolError("content is required for replace")
        mid = await _resolve_entry_id()
        if action == "update":
            ok = await update_memory(mid, content)
            if not ok:
                raise ToolError(f"memory#{mid} not found")
            await enqueue_embedding(mid, bump=True)
            return ToolResult(content=f"memory#{mid} updated")
        verdict = await review_write(content, kind="memory")
        if not verdict.allowed:
            raise ToolError(f"memory write blocked by guard: {verdict.reason}")
        write_origin = ORIGIN_AUTO_EXTRACT if is_auto_extract_write() else None
        ok = await update_memory(mid, content, anchor=anchor, origin=write_origin)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        await enqueue_embedding(mid, bump=True)
        origin_label = " [auto_extract]" if write_origin == ORIGIN_AUTO_EXTRACT else ""
        return ToolResult(content=f"memory#{mid} replaced{origin_label}")

    if action == "remove":
        mid = await _resolve_entry_id(for_remove=True)
        ok = await delete_memory(mid)
        if not ok:
            raise ToolError(f"memory#{mid} not found")
        return ToolResult(content=f"memory#{mid} removed")

    if action == "read":
        rows = await list_memories(limit=int(args.get("limit", 100) or 100))
        scoped = [r for r in rows if str(r.get("anchor") or "experience") == anchor]
        if not scoped:
            return ToolResult(content="(empty)")
        return ToolResult(
            content="\n".join(f"- #{r['id']} {r['content']}" for r in scoped),
            metadata={"items": scoped},
        )

    if action == "list":
        rows = await list_memories(limit=int(args.get("limit", 50) or 50))
        if not rows:
            return ToolResult(content="(empty)")
        return ToolResult(
            content="\n".join(f"#{r['id']}[{r['embedding_state']}] {r['content']}" for r in rows),
            metadata={"items": rows},
        )

    if action == "recall":
        query = pick_str(args, "query")
        if not query:
            raise ToolError("query is required for recall")
        top_k = int(args.get("top_k", 5) or 5)
        hits = await recall_items(query, top_k=top_k)
        scoped = [h for h in hits if str(h.get("anchor") or "experience") == anchor]
        if not scoped:
            return ToolResult(content="(no recall hits)")
        return ToolResult(
            content="\n".join(
                f"- #{h['id']} [{h.get('anchor', 'experience')}] {h['content']}" for h in scoped
            ),
            metadata={"items": scoped},
        )

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
            "不要保存：单次问答摘要、任务进度、会话结果、已完成工作日志、临时 TODO；"
            "这些用 session_recall。可复用的做法应沉淀为 skill。\n\n"
            "target：user=用户画像，memory=经验笔记。\n"
            "动作：add / replace / remove / read / list / recall；update、delete 为兼容别名。\n"
            "replace/remove/update/delete：优先传 snapshot/read/list/recall 中的 id；"
            "否则 old_text（或 remove 时可用 content）为唯一匹配子串。\n"
            "replace/update 的新正文用 content（别名 new_string）。"
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
                "id": {
                    "type": "integer",
                    "description": "Entry id from snapshot, read, list, or recall.",
                },
                "content": {
                    "type": "string",
                    "description": "New full text for add/replace/update; for remove, may identify the entry.",
                },
                "old_text": {
                    "type": "string",
                    "description": "Unique substring when id is unknown. Alias: old_string.",
                },
                "query": {"type": "string", "description": "Required for recall."},
                "top_k": {"type": "integer", "default": 5},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["action"],
        },
        handler=_memory_tool,
    )
)
