"""env_vars 工具：环境变量 KV 的增删改查与召回。"""

from __future__ import annotations

from typing import Any

from ..env_vars import add_env_var, delete_env_var, list_env_vars, recall_env_vars, update_env_var
from .args import pick_action, pick_int, pick_str
from .base import Tool, ToolError, ToolResult, register_builtin


async def _select_env_var_by_name(name: str) -> int:
    key = name.strip()
    if not key:
        raise ToolError("name is required")
    rows = await list_env_vars(limit=500)
    matches = [r for r in rows if str(r.get("name") or "").strip() == key]
    if not matches:
        raise ToolError(f"env var not found: {key}")
    if len(matches) > 1:
        raise ToolError(f"multiple env vars named '{key}'; use id instead")
    return int(matches[0]["id"])


async def _resolve_env_var_id(args: dict[str, Any]) -> int:
    env_id = pick_int(args, "id")
    if env_id:
        return env_id
    name = pick_str(args, "name")
    if name:
        return await _select_env_var_by_name(name)
    raise ToolError("id or name is required (use id from list/recall, or exact variable name)")


async def _env_vars_tool(args: dict[str, Any]) -> ToolResult:
    action = pick_action(args)

    if action == "add":
        name = pick_str(args, "name")
        value = pick_str(args, "value")
        description = pick_str(args, "description")
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
        env_id = await _resolve_env_var_id(args)
        name = args.get("name")
        value = args.get("value")
        description = args.get("description")
        if name is None and value is None and description is None:
            raise ToolError("at least one of name, value, or description is required for update")
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
        env_id = await _resolve_env_var_id(args)
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
        query = pick_str(args, "query")
        if not query:
            raise ToolError("query is required for recall")
        top_k = int(args.get("top_k", 5) or 5)
        rows = await recall_env_vars(query, top_k=top_k)
        if not rows:
            return ToolResult(content="(no recall hits)")
        return ToolResult(
            content="\n".join(
                f"- #{r['id']} {r['name']}={r['value']}"
                + (f" // {r['description']}" if r.get("description") else "")
                for r in rows
            ),
            metadata={"items": rows},
        )

    raise ToolError(f"unknown action: {action}")


register_builtin(
    Tool(
        name="env_vars",
        description=(
            "Manage workspace env-var knowledge base (name/value/description) with semantic recall."
            "For config keys, endpoints, non-secret runtime params, team conventions."
            "Actions: add / update / delete / list / recall."
            "For update/delete: prefer id from list/recall; else exact name. "
            "Do not use when the user only asks about code logic, not config persistence."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "update", "delete", "list", "recall"],
                },
                "id": {
                    "type": "integer",
                    "description": "Record id from list/recall. Preferred for update/delete.",
                },
                "name": {
                    "type": "string",
                    "description": "Variable name (required for add; optional lookup for update/delete).",
                },
                "value": {
                    "type": "string",
                    "description": "Variable value (required for add).",
                },
                "description": {"type": "string", "description": "Human-readable note for the variable."},
                "query": {"type": "string", "description": "Required for recall."},
                "top_k": {"type": "integer", "default": 5},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["action"],
        },
        handler=_env_vars_tool,
    )
)
