import type { ChatPart } from "./model";

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
    if (part.type !== "tool" || part.running || !isTodoTool(part.toolName)) continue;
    const plan = parseTodoPlan(part.preview);
    if (plan) latest = plan;
  }
  return latest;
}

export { isTodoTool };
