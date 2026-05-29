"""env_vars 工具：环境变量 KV 的增删改查与召回。"""

from __future__ import annotations

from typing import Any

from ..env_vars import add_env_var, delete_env_var, list_env_vars, recall_env_vars, update_env_var
from .base import Tool, ToolError, ToolResult, register_builtin


async def _env_vars_tool(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action", "")).lower()

    if action == "add":
        name = str(args.get("name", "")).strip()
        value = str(args.get("value", "")).strip()
        description = str(args.get("description", "")).strip()
        if not name:
            raise ToolError("name is required for add")
        if not value:
            raise ToolError("value is required for add")
        try:
            env_id = await add_env_var(name, value, description)
        except FileExistsError:
            raise ToolError(f"env var already exists: {name}") from None
        return ToolResult(content=f"env_var#{env_id} saved")

    if action == "update":
        env_id = int(args.get("id", 0) or 0)
        if not env_id:
            raise ToolError("id is required for update")
        name = args.get("name")
        value = args.get("value")
        description = args.get("description")
        if name is None and value is None and description is None:
            raise ToolError("at least one field is required for update")
        try:
            ok = await update_env_var(
                env_id,
                name=str(name).strip() if name is not None else None,
                value=str(value).strip() if value is not None else None,
                description=str(description) if description is not None else None,
            )
        except FileExistsError:
            raise ToolError(f"env var already exists: {name}") from None
        if not ok:
            raise ToolError(f"env_var#{env_id} not found")
        return ToolResult(content=f"env_var#{env_id} updated")

    if action == "delete":
        env_id = int(args.get("id", 0) or 0)
        if not env_id:
            raise ToolError("id is required for delete")
        ok = await delete_env_var(env_id)
        if not ok:
            raise ToolError(f"env_var#{env_id} not found")
        return ToolResult(content=f"env_var#{env_id} deleted")

    if action == "list":
        limit = int(args.get("limit", 100) or 100)
        rows = await list_env_vars(limit=limit)
        if not rows:
            return ToolResult(content="(empty)")
        return ToolResult(
            content="\n".join(
                f"#{r['id']}[{r['embedding_state']}] {r['name']}={r['value']}"
                + (f" // {r['description']}" if r.get("description") else "")
                for r in rows
            ),
            metadata={"items": rows},
        )

    if action == "recall":
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolError("query is required for recall")
        top_k = int(args.get("top_k", 5) or 5)
        rows = await recall_env_vars(query, top_k=top_k)
        if not rows:
            return ToolResult(content="(no recall hits)")
        return ToolResult(
            content="\n".join(
                f"- {r['name']}={r['value']}" + (f" // {r['description']}" if r.get("description") else "")
                for r in rows
            ),
            metadata={"items": rows},
        )

    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="env_vars",
        description=(
            "管理工作区级环境变量知识库（名称/值/说明）并支持语义召回。"
            "适用于保存和复用配置项、端点、非敏感运行参数与团队约定变量。"
            "优先动作：add/update/delete/list/recall。"
            "当用户只是询问代码逻辑而非配置沉淀时，不应调用本工具。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "update", "delete", "list", "recall"],
                    "description": "操作类型：新增/更新/删除/列表/语义召回。",
                },
                "id": {"type": "integer", "description": "变量记录 ID（update/delete 必填）。"},
                "name": {"type": "string", "description": "变量名（add 必填；update 可选）。"},
                "value": {"type": "string", "description": "变量值（add 必填；update 可选）。"},
                "description": {"type": "string", "description": "变量说明（便于团队理解用途）。"},
                "query": {"type": "string", "description": "召回查询词（recall 必填）。"},
                "top_k": {"type": "integer", "default": 5, "description": "recall 返回条数上限。"},
                "limit": {"type": "integer", "default": 100, "description": "list 返回条数上限。"},
            },
            "required": ["action"],
        },
        handler=_env_vars_tool,
    )
)
