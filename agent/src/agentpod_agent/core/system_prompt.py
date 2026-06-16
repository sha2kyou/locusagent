"""System prompt 三层动态组装与 session 级缓存（对齐 Hermes stable/context/volatile）。

- stable：身份、工具规则、技能目录、产物类目 — session 内缓存，保 prefix cache 温热
- context：工作区资源摘要（技能/MCP/记忆/env/定时任务/产物），每轮重建
- volatile：记忆快照、会话元数据 — 每轮重建，记忆写入后下轮自动可见
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TypedDict

from ..artifacts import list_categories
from ..config import get_settings
from ..host_settings import get_timezone
from ..memory import list_memories, memory_term_label
from ..skills import list_skills
from ..logging import get_logger
from ..tool_settings import is_skill_enabled, load_tool_settings
from ..tools import registry as tool_registry
from ..workspace import get_workspace_id
from .persistence import get_session_system_prompt, set_session_system_prompt

log = get_logger("system_prompt")

_SNAPSHOT_MEMORY_LIMIT = 30
_CTX_DELIMITER = "\n<<AGENTPOD_CTX>>\n"
# 变更 stable 模板时递增，使旧 session 缓存自动失效。
FROZEN_SYSTEM_PROMPT_VERSION = 26
_CACHE_PREFIX = f"agentpod:sp:v{FROZEN_SYSTEM_PROMPT_VERSION}:"

MEMORY_GUIDANCE = (
    "你拥有跨会话的持久记忆。用 memory 工具保存长期有效的事实：用户偏好、环境细节、稳定约定。"
    "每轮都会注入记忆快照——条目应紧凑，只保留后续仍重要的信息；优先记录能减少用户反复叮嘱的内容。\n"
    "不要将任务进度、会话结果、完工日志或临时状态写入记忆；回顾历史对话用 session_recall 或 session_search。"
    "不要记录合并请求编号、议题编号、提交哈希，或一周内会过时的信息。"
    "若发现可复用的技巧或工作流，应写入私有技能而非记忆。\n"
    "以陈述性事实书写记忆。term=long_term 存稳定用户事实与偏好（长期记忆）；"
    "term=short_term 存持久操作笔记（短期记忆）。兼容 target=user/memory。"
)

SKILLS_GUIDANCE = (
    "下方列出了精简的技能目录。当某技能相关时，调用 skill_view{name} 按需加载完整正文，不要臆测其内容。"
    "仅私有技能可通过 skill_manage 修改；共享与内置技能只读。"
)

SESSION_SEARCH_GUIDANCE = (
    "当用户提及记忆快照中不存在的过往对话或结论时，先使用 session_recall 或 session_search，不要猜测。"
)

ARTIFACT_GUIDANCE = (
    "artifact_save 用于保存用户明确要求保存或归档的交付物。"
    "可下载的工作区文件用 deliver_file。"
    "当用户提及已保存的产物时，先调用 artifact_recall{query}。"
)

TOOL_LOOP_LIMIT_GUIDANCE = (
    "当工具调用轮次、循环护栏或上下文限制迫使你停止继续调工具时，"
    "必须基于对话与工具结果中已有的信息，向用户输出完整的中文总结答复："
    "已完成的进展、当前结论、未完成项与原因、建议的下一步。"
    "不要沉默结束，不要返回空回复，也不要再尝试调用工具。"
)


class SystemPromptParts(TypedDict):
    stable: str
    context: str
    volatile: str


def _format_available_tools() -> set[str]:
    return {t.name for t in tool_registry.list(workspace_id=get_workspace_id())}


async def _compute_stable_fingerprint() -> str:
    tool_settings = load_tool_settings()
    enabled_tools = sorted(_format_available_tools())
    skills = sorted(
        f"{s.name}:{(s.description or '').strip()}"
        for s in list_skills()
        if is_skill_enabled(s.name)
    )
    category_rows = await list_categories()
    categories = sorted(
        f"{str(c.get('name') or '').strip()}:{str(c.get('description') or '').strip()}"
        for c in category_rows
        if str(c.get("name") or "").strip()
    )
    payload = {
        "tools": enabled_tools,
        "tool_settings": tool_settings.to_dict(),
        "skills": skills,
        "categories": categories,
        "version": FROZEN_SYSTEM_PROMPT_VERSION,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:16]


def _wrap_stable_context_cache(stable: str, context: str, fingerprint: str) -> str:
    return f"{_CACHE_PREFIX}{fingerprint}:\n{stable}{_CTX_DELIMITER}{context}"


def _unwrap_stable_context_cache(cached: str, fingerprint: str) -> tuple[str, str] | None:
    expected_prefix = f"{_CACHE_PREFIX}{fingerprint}:"
    if not cached.startswith(expected_prefix):
        return None
    body = cached[len(expected_prefix) + 1 :]
    if _CTX_DELIMITER not in body:
        return None
    stable, context = body.split(_CTX_DELIMITER, 1)
    return stable, context


async def _build_memory_snapshot() -> list[str]:
    rows = await list_memories(limit=_SNAPSHOT_MEMORY_LIMIT)
    if not rows:
        return []
    rows_sorted = sorted(rows, key=lambda r: 0 if str(r.get("anchor")) == "identity" else 1)
    out: list[str] = []
    seen: set[str] = set()
    for r in rows_sorted:
        text = str(r.get("content") or "").strip()
        mid = int(r.get("id") or 0)
        if text and text not in seen:
            seen.add(text)
            label = memory_term_label(r.get("anchor"))
            out.append(f"#{mid} [{label}] {text}")
    return out


async def build_stable_prompt() -> str:
    skills = [s for s in list_skills() if is_skill_enabled(s.name)]
    settings = get_settings()
    tool_names = sorted(_format_available_tools())
    enabled = set(tool_names)
    pieces = [
        f"你是在 AgentPod 桌面应用中运行的 AI 代理。",
        f"在合适时使用提供的工具。可用工具：{', '.join(tool_names)}。",
        "仅通过原生 tool_calls 调用工具，切勿在消息正文中书写工具调用。"
        "不要输出伪工具标签、伪函数调用、伪参数、JSON 工具桩或任何文本形式的工具模拟，此类内容不会被执行。"
        "需要工具时发出 tool_calls，正文保持为空或仅面向用户的说明。",
        "并行工具调用：当多个工具调用彼此独立（一个的输出不是另一个入参所必需）时，"
        "在同一轮助手回复中一次性发出多个 tool_calls，它们会并行执行。"
        "用户要求同时获取、搜索或阅读多项内容时，优先并行而非每轮只调一个工具"
        "（例如多个 read_file 路径、多个网址、search_files 与 web_search 组合、MCP 读/列操作）。"
        "不要为了等第 N 轮结果才发出本可并行的第 N+1 轮独立调用。"
        "例外：clarify 必须单独调用，不得与其他工具并行；clarify 成功后立即结束本轮，不再输出。"
        "不要并行调用会修改状态的工具，也不要并行化前后步骤有依赖的调用。",
        TOOL_LOOP_LIMIT_GUIDANCE,
        "当方向或偏好会显著影响输出（如命名、设计风格、范围、技术选型）时，"
        "通过 clarify 向用户提问，参数为严格 JSON：{question, choices, allow_other}（2–4 个互斥选项，单选）。"
        "所有可选项写在 choices 中，不要写在 question 里。"
        "每轮最多问一个问题：每轮至多调用一次 clarify，且不得并行；"
        "若有多项待澄清，分多轮逐一询问。clarify 成功后立即结束本轮。"
        "以下情况跳过 clarify：选项无法枚举、用户须多选、任意合理选择均可、或用户明确要求直接执行。",
        "多步任务应使用 todo 工具，何时拆解、何时跳过，遵循 todo 工具描述中的规则。",
        "工作区文件位于当前工作区目录下的 workspace/；私有技能位于工作区 skills/ 目录。",
        "工作区内文件操作用 read_file、search_files、write_file、patch。",
        "manage_workspace 仅用于 MCP 服务配置与环境摘要，"
        "不得用于创建、删除、重命名或切换 AgentPod 工作区。"
        "你只在用户当前工作区内操作；若用户在对话中要求创建/删除/重命名/切换工作区，"
        "应拒绝并告知其在对话外的网页「工作区」页面操作。",
        "用户无法从界面直接浏览本地文件系统。",
        "除非用户明确要求保存、导出或归档，否则直接在对话中以正文或代码块交付结果。"
        "用户需要下载工作区文件（文档、压缩包、表格、二进制等）时，写入 workspace/ 并调用 deliver_file，不要用 artifact_save。"
        "对话界面会自动显示下载入口；deliver_file 成功后不要在回复中提及文件："
        "不要说已发送、不要写文件名、不要写 Markdown 或 HTTP 链接、不要写产物路径或附件编号。"
        "仅在用户需要上下文时，最多用一句可选说明描述文件内容。",
        "对话中的数学公式用 LaTeX 以便前端渲染：行内 $...$，独立成行块级 $$...$$（块级公式前后各空一行）。"
        "不要用普通 Unicode 符号替代公式，不要把公式放在普通代码围栏里。"
        "矩阵、分段函数等环境内换行用 \\\\。"
        "示例矩阵：$$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$$；"
        "示例分段：$$\\begin{cases} x + y = 5 \\\\ 2x - y = 1 \\end{cases}$$。",
        "执行代码前，仅当请求依赖外部资源时，才核实所需上下文（接口密钥、数据库连接、时区或路径依赖）。"
        "凭据与配置用 env_vars，运行时身份与时区用 get_current_user；否则直接执行。",
        "用户询问当前日期或时间时，使用运行时时间上下文中的「当前用户本地时间」，不要编造或估算。",
        "用户明确要求交付物（创建、生成并保存、导出、归档、产物）时，调用 artifact_save 归档。"
        "按渲染需求显式设置 type：markdown（Markdown 渲染）、latex（LaTeX/数学，行内 $...$ 或块级 $$...$$）、"
        "text（纯文本，不做 Markdown 或 LaTeX 渲染，原样存储与展示）。"
        "artifact_save 的 JSON 参数中，LaTeX 命令的反斜杠须写两次（例如 \\\\begin 而非 \\begin）。"
        "若提供 category，起草内容时必须阅读并遵循下方「产物类目（已有）」中该类目的描述"
        "（这是提示指引，除非用户要求，不要把类目描述原文写入产物正文）。"
        "目标类目不存在时，先调用 artifact_category_create。"
        "若 artifact_category_create 提示存在相似类目，先 clarify 再决定复用或新建。"
        "代码类产物用 type=markdown，正文须包在代码围栏中（```语言\\n...代码...\\n```）。"
        "artifact_save 成功后，在回复中简短确认已保存，不要附带产物链接。",
    ]
    tool_guidance: list[str] = []
    if "memory" in enabled:
        tool_guidance.append(MEMORY_GUIDANCE)
    if "session_search" in enabled or "session_recall" in enabled:
        tool_guidance.append(SESSION_SEARCH_GUIDANCE)
    if "skill_view" in enabled or "skill_manage" in enabled:
        tool_guidance.append(SKILLS_GUIDANCE)
    if "artifact_save" in enabled:
        tool_guidance.append(ARTIFACT_GUIDANCE)
    if tool_guidance:
        pieces.append(" ".join(tool_guidance))
    if skills:
        pieces.append("\n## 可用技能目录")
        for s in skills:
            triggers = "、".join(s.triggers[:5]) if s.triggers else "无"
            desc = (s.description or "").strip() or "（无描述）"
            pieces.append(f"- {s.name} [{s.source}] 触发词：{triggers} · {desc}")
    categories = await list_categories()
    if categories:
        pieces.append("\n## 产物类目（已有）")
        pieces.append("优先复用已有类目名称；仅在必要时通过 artifact_category_create 创建新类目。")
        for c in categories:
            name = str(c.get("name") or "").strip()
            if not name:
                continue
            desc = str(c.get("description") or "").strip()
            if desc:
                pieces.append(f"- {name}：{desc}")
            else:
                pieces.append(f"- {name}")
    return "\n".join(pieces)


_CONTEXT_HEADER = (
    "以下为当前工作区资源快照（只读）；环境变量仅列名称与说明，不含取值。"
    "需要完整列表或修改时请用对应专用工具（manage_workspace、env_vars、mcp_manage 等）。"
)


async def build_context_prompt(*, session_id: str | None = None) -> str:
    """Context 层：工作区资源摘要，与 manage_workspace 工具同源。"""
    _ = session_id
    from ..workspace import get_workspace_id
    from ..workspace_summary import build_workspace_summary

    summary, _ = await build_workspace_summary()
    if not summary.strip():
        return ""
    wid = get_workspace_id()
    return f"## 工作区上下文（{wid}）\n{_CONTEXT_HEADER}\n\n{summary}"


async def build_volatile_prompt(*, session_id: str | None = None) -> str:
    """Volatile 层：每轮重建的记忆快照与会话元数据。"""
    parts: list[str] = []
    snapshot = await _build_memory_snapshot()
    if snapshot:
        parts.append("## 记忆（当前快照）")
        parts.append(
            "每行格式为 #编号 [用户|记忆]。"
            "新增用 memory(action=add)，更新用 memory(action=replace, id=..., content=...)。"
            "凭据与配置键值用 env_vars。"
        )
        parts.extend(f"- {m}" for m in snapshot)
    now_utc = datetime.now(UTC)
    date_line = f"对话日期：{now_utc.strftime('%Y年%m月%d日')}（协调世界时）"
    try:
        tz_name = await get_timezone()
        date_line += f"\n用户时区：{tz_name}"
    except Exception:
        pass
    if session_id:
        date_line += f"\n会话编号：{session_id}"
    parts.append(date_line)
    return "\n".join(parts)


async def build_system_prompt_parts(*, session_id: str | None = None) -> SystemPromptParts:
    return {
        "stable": await build_stable_prompt(),
        "context": await build_context_prompt(session_id=session_id),
        "volatile": await build_volatile_prompt(session_id=session_id),
    }


def assemble_system_prompt(parts: SystemPromptParts) -> str:
    return "\n\n".join(p.strip() for p in (parts["stable"], parts["context"], parts["volatile"]) if p and p.strip())


async def _get_or_create_stable_context(session_id: str) -> tuple[str, str]:
    fingerprint = await _compute_stable_fingerprint()
    cached = await get_session_system_prompt(session_id)
    if cached:
        parsed = _unwrap_stable_context_cache(cached, fingerprint)
        if parsed is not None:
            return parsed
    stable = await build_stable_prompt()
    context = await build_context_prompt(session_id=session_id)
    await set_session_system_prompt(
        session_id,
        _wrap_stable_context_cache(stable, context, fingerprint),
    )
    return stable, context


async def get_cached_stable_context(session_id: str) -> SystemPromptParts:
    """供 background review fork 继承父会话 stable+context（不含 volatile）。"""
    stable, context = await _get_or_create_stable_context(session_id)
    return {"stable": stable, "context": context, "volatile": ""}


async def get_or_create_system_prompt(session_id: str) -> str:
    stable, _ = await _get_or_create_stable_context(session_id)
    context = await build_context_prompt(session_id=session_id)
    volatile = await build_volatile_prompt(session_id=session_id)
    return assemble_system_prompt({"stable": stable, "context": context, "volatile": volatile})


# 兼容旧测试与调用方
def _wrap_system_prompt_cache(prompt: str, fingerprint: str) -> str:
    return _wrap_stable_context_cache(prompt, "", fingerprint)


def _unwrap_system_prompt_cache(cached: str, fingerprint: str) -> str | None:
    parsed = _unwrap_stable_context_cache(cached, fingerprint)
    if parsed is None:
        return None
    stable, context = parsed
    return assemble_system_prompt({"stable": stable, "context": context, "volatile": ""})


async def build_frozen_system_prompt() -> str:
    """兼容旧调用：返回完整三层组装（volatile 实时）。"""
    parts = await build_system_prompt_parts()
    return assemble_system_prompt(parts)
