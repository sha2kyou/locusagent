"""manage_workspace：工作区环境摘要（只读）。

返回技能、MCP、记忆、环境变量、定时任务、产物的条数与各自最近 5 条数据。
MCP 的增删改操作走 mcp_manage 工具。
"""

from __future__ import annotations

from typing import Any

from ..db import conn_scope, run_in_thread
from ..env_vars import list_env_vars
from ..memory import count_memories, list_memories
from ..mcp_.config import list_mcp_servers
from ..skills import list_skills
from ..tool_settings import is_mcp_server_enabled, is_skill_enabled
from .base import Tool, ToolResult, register_builtin


def _mcp_runtime() -> dict[str, dict[str, Any]]:
    from ..mcp_.client import list_mcp_runtime
    return list_mcp_runtime()


async def _count_artifacts() -> int:
    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            (n,) = c.execute("SELECT COUNT(*) FROM artifacts").fetchone()
            return int(n)
    return await run_in_thread(_do)


async def _recent_artifacts(limit: int = 5) -> list[dict[str, Any]]:
    def _do() -> list[dict[str, Any]]:
        with conn_scope(load_vec=False) as c:
            rows = c.execute(
                "SELECT a.id, a.title, a.type, ac.name AS category "
                "FROM artifacts a "
                "LEFT JOIN artifact_categories ac ON a.category_id = ac.id "
                "ORDER BY a.created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
    return await run_in_thread(_do)


async def _manage_workspace(_args: dict[str, Any]) -> ToolResult:
    lines: list[str] = []
    meta: dict[str, Any] = {}

    # ── 技能 ──────────────────────────────────────────────────
    all_skills = [s for s in await run_in_thread(list_skills) if is_skill_enabled(s.name)]
    skill_count = len(all_skills)
    # 私有技能优先展示，再是公共；最多取 5 条
    private_skills = [s for s in all_skills if s.source == "private"]
    public_skills = [s for s in all_skills if s.source != "private"]
    recent_skills = (private_skills + public_skills)[:5]
    lines.append(f"## 技能 ({skill_count})")
    for s in recent_skills:
        lines.append(f"- {s.name} [{s.source}]: {s.description[:60]}")
    if not recent_skills:
        lines.append("- (空)")
    meta["skills"] = {"count": skill_count, "items": [s.to_dict() for s in recent_skills]}

    # ── MCP ───────────────────────────────────────────────────
    servers = [s for s in await run_in_thread(list_mcp_servers) if is_mcp_server_enabled(s.name)]
    mcp_count = len(servers)
    runtime = _mcp_runtime()
    recent_mcp = servers[:5]
    lines.append(f"\n## MCP ({mcp_count})")
    for s in recent_mcp:
        r = runtime.get(s.name, {})
        connected = bool(r.get("connected", False))
        tool_count = len(r.get("tools", []))
        addr = s.url if s.transport == "http" else " ".join((s.command + s.args)[:3])
        lines.append(f"- {s.name} [{s.transport}] connected={connected} tools={tool_count} | {addr}")
    if not recent_mcp:
        lines.append("- (空)")
    meta["mcp"] = {
        "count": mcp_count,
        "items": [
            {**s.to_public_dict(), "connected": bool(runtime.get(s.name, {}).get("connected", False))}
            for s in recent_mcp
        ],
    }

    # ── 记忆 ──────────────────────────────────────────────────
    mem_count = await count_memories()
    recent_mem = await list_memories(limit=5)
    lines.append(f"\n## 记忆 ({mem_count})")
    for m in recent_mem:
        snippet = str(m.get("content") or "")[:60]
        anchor = str(m.get("anchor") or "experience")
        lines.append(f"- #{m['id']} [{anchor}]: {snippet}")
    if not recent_mem:
        lines.append("- (空)")
    meta["memory"] = {"count": mem_count, "items": recent_mem}

    # ── 环境变量 ──────────────────────────────────────────────
    env_rows = await list_env_vars(limit=5)

    async def _count_env() -> int:
        def _do() -> int:
            with conn_scope(load_vec=False) as c:
                (n,) = c.execute("SELECT COUNT(*) FROM env_vars").fetchone()
                return int(n)
        return await run_in_thread(_do)

    env_count = await _count_env()
    lines.append(f"\n## 环境变量 ({env_count})")
    for e in env_rows:
        desc = str(e.get("description") or "").strip()
        suffix = f" — {desc}" if desc else ""
        lines.append(f"- {e['name']}{suffix}")
    if not env_rows:
        lines.append("- (空)")
    # 不输出 value，避免敏感信息泄漏
    meta["env_vars"] = {
        "count": env_count,
        "items": [{"id": e["id"], "name": e["name"], "description": e.get("description")} for e in env_rows],
    }

    # ── 定时任务 ──────────────────────────────────────────────
    tasks: list[dict[str, Any]] = []
    task_count = 0
    try:
        from ..host_scheduled_tasks import list_scheduled_tasks
        tasks = await list_scheduled_tasks()
        task_count = len(tasks)
    except Exception:
        pass
    recent_tasks = sorted(tasks, key=lambda t: t.get("created_at") or "", reverse=True)[:5]
    lines.append(f"\n## 定时任务 ({task_count})")
    for t in recent_tasks:
        status = str(t.get("last_run_status") or "idle")
        enabled = "enabled" if t.get("enabled") else "disabled"
        trigger = str(t.get("cron_expr") or t.get("run_at") or "—")
        lines.append(f"- #{t['id']} {t.get('title', '')} [{enabled}] {trigger} | {status}")
    if not recent_tasks:
        lines.append("- (空)")
    meta["scheduled_tasks"] = {"count": task_count, "items": recent_tasks}

    # ── 产物 ──────────────────────────────────────────────────
    art_count = await _count_artifacts()
    recent_arts = await _recent_artifacts(5)
    lines.append(f"\n## 产物 ({art_count})")
    for a in recent_arts:
        cat = str(a.get("category") or "—")
        lines.append(f"- {a.get('title')} [{a.get('type')}] ({cat})")
    if not recent_arts:
        lines.append("- (空)")
    meta["artifacts"] = {"count": art_count, "items": recent_arts}

    return ToolResult(content="\n".join(lines), metadata=meta)


register_builtin(
    Tool(
        name="manage_workspace",
        description=(
            "工作区环境摘要（只读）。"
            "返回技能、MCP、记忆、环境变量、定时任务、产物的条数与各自最近 5 条数据。"
            "MCP 的增删改请用 mcp_manage；其他资源 CRUD 走对应专用工具。"
        ),
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_manage_workspace,
    )
)
