import { AlertCircle, Check, Circle, ListTodo, Loader2, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { CollapsibleMetaBlock } from "./CollapsibleMetaBlock";
import type { TodoPlan, TodoStep, TodoStepStatus } from "./todo";

function StepIcon({ status }: { status: TodoStepStatus }) {
  if (status === "done") {
    return <Check className="size-4 shrink-0 text-emerald-500" strokeWidth={2.5} />;
  }
  if (status === "in_progress") {
    return <Loader2 className="size-4 shrink-0 animate-spin text-brand" />;
  }
  if (status === "interrupted") {
    return <AlertCircle className="size-4 shrink-0 text-destructive" />;
  }
  if (status === "skipped") {
    return <Minus className="size-4 shrink-0 text-muted-foreground" />;
  }
  return <Circle className="size-3.5 shrink-0 text-muted-foreground/50" />;
}

function TodoStepRow({ step, index }: { step: TodoStep; index: number }) {
  const active = step.status === "in_progress";
  const done = step.status === "done";
  const skipped = step.status === "skipped";
  const interrupted = step.status === "interrupted";
  return (
    <li className="relative flex gap-3 pb-3.5 last:pb-0">
      <div className="flex flex-col items-center">
        <StepIcon status={step.status} />
        <span
          className="mt-1.5 w-px flex-1 last:hidden"
          style={{ background: "linear-gradient(to bottom, var(--color-border-strong) 0%, var(--color-border) 60%, transparent 100%)" }}
          aria-hidden
        />
      </div>
      <div className="min-w-0 flex-1 pb-0.5 pt-px">
        <div className="flex items-center gap-1.5">
          <span className="shrink-0 tabular-nums text-[10px] text-muted-foreground/60">{index + 1}.</span>
          <span
            className={cn(
              "text-[13px] leading-snug",
              active && "font-medium text-foreground",
              done && "text-foreground/90",
              skipped && "text-muted-foreground/60 line-through",
              interrupted && "text-destructive/90",
              !active && !done && !skipped && !interrupted && "text-muted-foreground",
            )}
          >
            {step.title}
          </span>
        </div>
        {step.detail && !done && !interrupted ? (
          <p className="mt-0.5 pl-4 text-[11px] leading-relaxed text-muted-foreground/80">{step.detail}</p>
        ) : null}
        {step.note && (done || interrupted) ? (
          <p
            className={cn(
              "mt-0.5 pl-4 text-[11px] leading-relaxed",
              interrupted ? "text-destructive/70" : "text-muted-foreground/70",
            )}
          >
            {step.note}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function planSummary(plan: TodoPlan, t: ReturnType<typeof useTranslation>["t"]): string {
  const doneCount = plan.steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  const interruptedCount = plan.steps.filter((s) => s.status === "interrupted").length;
  if (interruptedCount > 0) {
    return t("chat.todo.summaryWithInterrupted", {
      done: doneCount,
      total: plan.steps.length,
      interrupted: interruptedCount,
    });
  }
  return t("chat.todo.summary", { done: doneCount, total: plan.steps.length });
}

export function TodoProgressPanel({ plan, active = false }: { plan: TodoPlan; active?: boolean }) {
  const { t } = useTranslation();
  return (
    <CollapsibleMetaBlock
      blockId={plan.plan_id}
      active={active}
      lockWhenActive={false}
      title={plan.title}
      activeTitle={t("chat.todo.activeTitle")}
      running={active}
      showRunningBadge
      icon={<ListTodo className="size-3.5" />}
      preview={planSummary(plan, t)}
      hidePreviewWhenOpen={false}
      className="border-brand/20 bg-brand/[0.035] ring-1 ring-inset ring-brand/10 shadow-sm"
    >
      <ol className="pl-1">
        {plan.steps.map((step, i) => (
          <TodoStepRow key={step.id} step={step} index={i} />
        ))}
      </ol>
    </CollapsibleMetaBlock>
  );
}
