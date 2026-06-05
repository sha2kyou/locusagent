"""用户请求是否应走 todo 拆解的轻量意图识别（规则，无 LLM）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBERED_ITEM_RE = re.compile(r"(?:^|\n)\s*\d+[\.)）、]\s+\S", re.MULTILINE)
_STEP_SEQ_RE = re.compile(r"(先.{1,40}(?:再|然后|接着)|分步|分阶段|按步骤|逐步|一步步)")
_MULTI_CLAUSE_RE = re.compile(r"[，,；;].+[，,；;]")
_DELIVERABLES_RE = re.compile(
    r"(?:API|接口|后端|前端|数据库|测试|部署|文档|页面|服务|模块)",
    re.IGNORECASE,
)
_BUILD_VERB_RE = re.compile(r"(?:实现|开发|搭建|构建|重构|迁移|设计并|编写|完成).{0,24}(?:功能|系统|模块|服务)?")
_FEATURE_BUILD_RE = re.compile(
    r"(?:实现|开发|搭建|编写|做).{0,24}(?:功能|系统|平台|模块|应用|app)",
    re.IGNORECASE,
)
_SIMPLE_QA_RE = re.compile(
    r"^\s*(?:什么是|是什么|为什么|怎么理解|解释一下|帮我总结|总结一下|翻译|查一下|告诉我)\b",
    re.IGNORECASE,
)
_SINGLE_SHOT_RE = re.compile(
    r"^\s*(?:读|打开|查看|列出|搜索|找|对比|比较).{0,32}$",
    re.IGNORECASE,
)
_EXPLICIT_TODO_RE = re.compile(r"(?:todo|任务列表|拆解|分步做|展示进度|跟踪进度)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TodoIntent:
    needs_todo: bool
    score: int
    reasons: tuple[str, ...]


def assess_todo_intent(user_text: str) -> TodoIntent:
    text = str(user_text or "").strip()
    if not text:
        return TodoIntent(needs_todo=False, score=0, reasons=())

    score = 0
    reasons: list[str] = []

    numbered = len(_NUMBERED_ITEM_RE.findall(text))
    if numbered >= 2:
        score += 3
        reasons.append(f"numbered_items={numbered}")
    elif numbered == 1:
        score += 1
        reasons.append("numbered_item=1")

    if _STEP_SEQ_RE.search(text):
        score += 2
        reasons.append("step_sequence")

    if _EXPLICIT_TODO_RE.search(text):
        score += 3
        reasons.append("explicit_todo")

    deliverables = len(_DELIVERABLES_RE.findall(text))
    if deliverables >= 2:
        score += 2
        reasons.append(f"deliverables={deliverables}")
    elif deliverables == 1 and _BUILD_VERB_RE.search(text):
        score += 1
        reasons.append("build+deliverable")

    if _FEATURE_BUILD_RE.search(text):
        score += 3
        reasons.append("feature_build")

    if _BUILD_VERB_RE.search(text) and len(text) >= 48:
        score += 1
        reasons.append("implementation_scope")

    if _MULTI_CLAUSE_RE.search(text) and len(text) >= 72:
        score += 1
        reasons.append("multi_clause")

    if _SIMPLE_QA_RE.search(text):
        score -= 3
        reasons.append("simple_qa")

    if _SINGLE_SHOT_RE.search(text):
        score -= 2
        reasons.append("single_shot")

    if len(text) < 28 and score < 3:
        score -= 1
        reasons.append("short_request")

    # 阈值 3：至少两条强信号或一条强信号 + 实施语境，避免简单问答误触
    needs_todo = score >= 3
    return TodoIntent(needs_todo=needs_todo, score=score, reasons=tuple(reasons))


_TODO_INTENT_MARKER = "## Todo intent (this turn)"


def messages_require_todo_intent(messages: list[dict[str, object]]) -> bool:
    for msg in messages:
        if msg.get("role") != "system":
            continue
        content = str(msg.get("content") or "")
        if content.startswith(_TODO_INTENT_MARKER):
            return True
    return False


def build_todo_intent_system_message(intent: TodoIntent) -> str:
    if not intent.needs_todo:
        return ""
    reason = ", ".join(intent.reasons) or "multi_step"
    return (
        f"{_TODO_INTENT_MARKER}\n"
        f"Assessment: multi-step work likely ({reason}; score={intent.score}, threshold=3). "
        "Before any mutating tool (write_file, patch, terminal, execute_code, memory/skill/artifact writes), "
        "call todo(action=create) with 2–20 ordered steps, then todo(action=confirm) for each step as you execute. "
        "Do not skip todo for this turn unless the request collapses to a single trivial action after inspection."
    )
