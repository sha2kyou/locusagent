"""工作区资源摘要（技能 / MCP / 记忆 / 环境变量 / 定时任务 / 产物）。"""

from __future__ import annotations

from typing import Any

from .db import conn_scope, run_in_thread
from .env_vars import list_env_vars
from .memory import count_memories, list_memories, memory_term_label
from .mcp_.config import list_mcp_servers
from .skills import list_skills
from .tool_settings import is_mcp_server_enabled, is_skill_enabled


def _mcp_runtime() -> dict[str, dict[str, Any]]:
    from .mcp_.client import list_mcp_runtime

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


async def _count_env_vars() -> int:
    def _do() -> int:
        with conn_scope(load_vec=False) as c:
            (n,) = c.execute("SELECT COUNT(*) FROM env_vars").fetchone()
            return int(n)

    return await run_in_thread(_do)


async def build_workspace_summary(*, recent_limit: int = 5) -> tuple[str, dict[str, Any]]:
    """返回 (Markdown 摘要正文, 结构化 metadata)。"""
    lines: list[str] = []
    meta: dict[str, Any] = {}
    limit = max(1, int(recent_limit))

    all_skills = [s for s in await run_in_thread(list_skills) if is_skill_enabled(s.name)]
    skill_count = len(all_skills)
    private_skills = [s for s in all_skills if s.source == "private"]
    public_skills = [s for s in all_skills if s.source != "private"]
    recent_skills = (private_skills + public_skills)[:limit]
    lines.append(f"## Skills ({skill_count})")
    for s in recent_skills:
        lines.append(f"- {s.name} [{s.source}]: {s.description[:60]}")
    if not recent_skills:
        lines.append("- (empty)")
    meta["skills"] = {"count": skill_count, "items": [s.to_dict() for s in recent_skills]}

    servers = [s for s in await run_in_thread(list_mcp_servers) if is_mcp_server_enabled(s.name)]
    mcp_count = len(servers)
    runtime = _mcp_runtime()
    recent_mcp = servers[:limit]
    lines.append(f"\n## MCP ({mcp_count})")
    for s in recent_mcp:
        r = runtime.get(s.name, {})
        connected = bool(r.get("connected", False))
        tool_count = len(r.get("tools", []))
        addr = s.url if s.transport == "http" else " ".join((s.command + s.args)[:3])
        lines.append(f"- {s.name} [{s.transport}] connected={connected} tools={tool_count} | {addr}")
    if not recent_mcp:
        lines.append("- (empty)")
    meta["mcp"] = {
        "count": mcp_count,
        "items": [
            {**s.to_public_dict(), "connected": bool(runtime.get(s.name, {}).get("connected", False))}
            for s in recent_mcp
        ],
    }

    mem_count = await count_memories()
    recent_mem = await list_memories(limit=limit)
    lines.append(f"\n## Memory ({mem_count})")
    for m in recent_mem:
        snippet = str(m.get("content") or "")[:60]
        term = memory_term_label(m.get("anchor"))
        lines.append(f"- #{m['id']} [{term}]: {snippet}")
    if not recent_mem:
        lines.append("- (empty)")
    meta["memory"] = {"count": mem_count, "items": recent_mem}

    env_rows = await list_env_vars(limit=limit)
    env_count = await _count_env_vars()
    lines.append(f"\n## Environment variables ({env_count})")
    for e in env_rows:
        desc = str(e.get("description") or "").strip()
        suffix = f" — {desc}" if desc else ""
        lines.append(f"- {e['name']}{suffix}")
    if not env_rows:
        lines.append("- (empty)")
    meta["env_vars"] = {
        "count": env_count,
        "items": [{"id": e["id"], "name": e["name"], "description": e.get("description")} for e in env_rows],
    }

    tasks: list[dict[str, Any]] = []
    task_count = 0
    try:
        from .host_scheduled_tasks import list_scheduled_tasks

        tasks = await list_scheduled_tasks()
        task_count = len(tasks)
    except Exception:
        pass
    recent_tasks = sorted(tasks, key=lambda t: t.get("created_at") or "", reverse=True)[:limit]
    lines.append(f"\n## Scheduled tasks ({task_count})")
    for t in recent_tasks:
        status = str(t.get("last_run_status") or "idle")
        enabled = "enabled" if t.get("enabled") else "disabled"
        trigger = str(t.get("cron_expr") or t.get("run_at") or "—")
        lines.append(f"- #{t['id']} {t.get('title', '')} [{enabled}] {trigger} | {status}")
    if not recent_tasks:
        lines.append("- (empty)")
    meta["scheduled_tasks"] = {"count": task_count, "items": recent_tasks}

    art_count = await _count_artifacts()
    recent_arts = await _recent_artifacts(limit)
    lines.append(f"\n## Artifacts ({art_count})")
    for a in recent_arts:
        cat = str(a.get("category") or "—")
        lines.append(f"- {a.get('title')} [{a.get('type')}] ({cat})")
    if not recent_arts:
        lines.append("- (empty)")
    meta["artifacts"] = {"count": art_count, "items": recent_arts}

    return "\n".join(lines), meta
