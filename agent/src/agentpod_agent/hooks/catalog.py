"""平台支持的 lifecycle hook 事件目录（单一真相源）。"""

from __future__ import annotations

from dataclasses import dataclass

from . import POST_USER_SUBMIT


@dataclass(frozen=True, slots=True)
class HookEventSpec:
    name: str
    summary: str
    when: str
    register: str
    callback_args: str
    notes: str = ""


SUPPORTED_HOOK_EVENTS: tuple[HookEventSpec, ...] = (
    HookEventSpec(
        name=POST_USER_SUBMIT,
        summary="用户消息被接受后的观测回调（不能拦截、改写 prompt 或注入 LLM 上下文）",
        when="每次用户提交之后、LLM 循环开始之前；聊天（submit_source=chat）与定时任务（submit_source=scheduled）均触发；重新生成也会触发（is_regenerate=true）",
        register="ctx.register_post_user_submit(callback)",
        callback_args=(
            "hook_name, session_id, user_message, user_message_id, attachment_ids, "
            "submit_source, is_regenerate, workspace_id（以及 **kwargs 前向兼容）"
        ),
        notes="source 为 submit_source 的兼容别名。单次回调默认 3s 超时，超时仅记日志。",
    ),
)


def format_hook_events_catalog() -> str:
    lines: list[str] = []
    for spec in SUPPORTED_HOOK_EVENTS:
        lines.append(f"### {spec.name}")
        lines.append(f"- 作用: {spec.summary}")
        lines.append(f"- 触发时机: {spec.when}")
        lines.append(f"- 注册方式: {spec.register}")
        lines.append(f"- 回调参数: {spec.callback_args}")
        if spec.notes:
            lines.append(f"- 说明: {spec.notes}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_hook_events_summary() -> str:
    """工具 description 用的单行摘要。"""
    names = ", ".join(spec.name for spec in SUPPORTED_HOOK_EVENTS)
    return (
        f"Supported hook events: {names}. "
        "Each hook.py defines register(ctx) and registers callbacks for these events. "
        "Currently post_user_submit runs after user message is accepted (observe-only, before LLM loop)."
    )
