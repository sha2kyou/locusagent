import type { ChatPart } from "./model";
import i18n from "../../i18n/index.ts";

export type TodoStepStatus = "pending" | "in_progress" | "done" | "skipped" | "interrupted";

export interface TodoStep {
  id: string;
  title: string;
  detail?: string;
  status: TodoStepStatus;
  note?: string;
}

export interface TodoPlan {
  plan_id: string;
  title: string;
  steps: TodoStep[];
  active_step_id?: string;
}

function isTodoTool(toolName: string): boolean {
  return toolName === "todo" || toolName.endsWith("/todo");
}

function normalizeStep(raw: unknown): TodoStep | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const id = String(row.id ?? "").trim();
  const title = String(row.title ?? "").trim();
  if (!id || !title) return null;
  const statusRaw = String(row.status ?? "pending").trim().toLowerCase();
  const status: TodoStepStatus =
    statusRaw === "in_progress" ||
    statusRaw === "done" ||
    statusRaw === "skipped" ||
    statusRaw === "interrupted"
      ? statusRaw
      : "pending";
  const step: TodoStep = { id, title, status };
  const detail = String(row.detail ?? "").trim();
  const note = String(row.note ?? "").trim();
  if (detail) step.detail = detail;
  if (note) step.note = note;
  return step;
}

export function parseTodoPlan(raw: unknown): TodoPlan | null {
  const text = typeof raw === "string" ? raw : raw && typeof raw === "object" ? JSON.stringify(raw) : "";
  if (!text.trim()) return null;
  try {
    const data = (typeof raw === "object" && raw ? raw : JSON.parse(text)) as Record<string, unknown>;
    if (!data || data.plan === null) return null;
    const planId = String(data.plan_id ?? "").trim();
    const title = String(data.title ?? "").trim();
    const stepsRaw = Array.isArray(data.steps) ? data.steps : [];
    const steps = stepsRaw.map(normalizeStep).filter((s): s is TodoStep => Boolean(s));
    if (!planId || !title || steps.length < 2) return null;
    const plan: TodoPlan = { plan_id: planId, title, steps };
    const active = String(data.active_step_id ?? "").trim();
    if (active) plan.active_step_id = active;
    return plan;
  } catch {
    return null;
  }
}

export function extractLatestTodoPlan(parts: ChatPart[]): TodoPlan | null {
  let latest: TodoPlan | null = null;
  for (const part of parts) {
    if (part.type !== "tool" || !isTodoTool(part.toolName)) continue;
    if (part.running && !part.preview) continue;
    const plan = parseTodoPlan(part.preview);
    if (plan) latest = plan;
  }
  return latest;
}

const STEP_STATUS_RANK: Record<TodoStepStatus, number> = {
  pending: 0,
  in_progress: 1,
  interrupted: 2,
  done: 3,
  skipped: 3,
};

function pickRicherStep(a: TodoStep, b: TodoStep): TodoStep {
  const rankA = STEP_STATUS_RANK[a.status];
  const rankB = STEP_STATUS_RANK[b.status];
  const primary = rankA >= rankB ? a : b;
  const secondary = rankA >= rankB ? b : a;
  return {
    ...primary,
    detail: primary.detail ?? secondary.detail,
    note: primary.note ?? secondary.note,
  };
}

/** 合并同 plan_id 的两份快照，逐步取更「 progressed 」的状态，避免 session / 消息源不一致。 */
export function mergeTodoPlans(primary: TodoPlan, secondary: TodoPlan): TodoPlan {
  if (primary.plan_id !== secondary.plan_id) return primary;
  const merged = new Map<string, TodoStep>();
  for (const step of secondary.steps) merged.set(step.id, step);
  for (const step of primary.steps) {
    const existing = merged.get(step.id);
    merged.set(step.id, existing ? pickRicherStep(step, existing) : step);
  }
  const steps = primary.steps.map((s) => merged.get(s.id)!);
  return { ...primary, title: primary.title || secondary.title, steps };
}

export function resolveTodoPlan(
  fromParts: TodoPlan | null,
  sessionTodoPlan: TodoPlan | null,
  isLastAssistant: boolean,
  hasTodoInMessage: boolean,
): TodoPlan | null {
  if (!isLastAssistant) {
    return fromParts ? applyHistoricalTodoInterrupt(fromParts) : null;
  }
  if (!hasTodoInMessage && !fromParts && !sessionTodoPlan) return null;
  if (sessionTodoPlan && fromParts) {
    if (sessionTodoPlan.plan_id === fromParts.plan_id) {
      return mergeTodoPlans(sessionTodoPlan, fromParts);
    }
    return sessionTodoPlan;
  }
  return sessionTodoPlan ?? fromParts ?? null;
}

/** 历史轮次气泡内的 todo 快照不会随 interrupt 更新，展示时补齐中断状态。 */
export function applyHistoricalTodoInterrupt(plan: TodoPlan): TodoPlan {
  let changed = false;
  const steps = plan.steps.map((step) => {
    if (step.status !== "pending" && step.status !== "in_progress") return step;
    changed = true;
    return {
      ...step,
      status: "interrupted" as const,
      note: step.note || i18n.t("chat.todo.interruptedNote"),
    };
  });
  if (!changed) return plan;
  const next: TodoPlan = { ...plan, steps };
  delete next.active_step_id;
  return next;
}

export { isTodoTool };
