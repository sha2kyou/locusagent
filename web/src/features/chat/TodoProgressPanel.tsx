import { useEffect, useState } from "react";
import { AlertCircle, Check, ChevronDown, Circle, ListTodo, Loader2, Minus } from "lucide-react";
import { ListCard } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { findScrollParent } from "@/lib/scroll-parent";
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
    <li className="relative flex gap-3 pb-4 last:pb-0">
      <div className="flex flex-col items-center">
        <StepIcon status={step.status} />
        <span className="mt-1 w-px flex-1 bg-border last:hidden" aria-hidden />
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] tabular-nums text-muted-foreground">{index + 1}</span>
          <span
            className={cn(
              "text-[13px] leading-snug",
              active && "font-medium text-foreground",
              done && "text-foreground",
              skipped && "text-muted-foreground line-through",
              interrupted && "text-destructive/90",
              !active && !done && !skipped && !interrupted && "text-muted-foreground",
            )}
          >
            {step.title}
          </span>
        </div>
        {step.detail && !done && !interrupted ? (
          <p className="mt-1 pl-5 text-xs leading-relaxed text-muted-foreground">{step.detail}</p>
        ) : null}
        {step.note && (done || interrupted) ? (
          <p
            className={cn(
              "mt-1 pl-5 text-xs leading-relaxed",
              interrupted ? "text-destructive/80" : "text-muted-foreground",
            )}
          >
            {step.note}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function planSummary(plan: TodoPlan): string {
  const doneCount = plan.steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  const interruptedCount = plan.steps.filter((s) => s.status === "interrupted").length;
  let text = `${doneCount}/${plan.steps.length} 步已完成`;
  if (interruptedCount > 0) text += ` · ${interruptedCount} 步已中断`;
  return text;
}

export function TodoProgressPanel({ plan }: { plan: TodoPlan }) {
  const hasActive = plan.steps.some((s) => s.status === "in_progress");
  const [open, setOpen] = useState(hasActive);

  useEffect(() => {
    if (hasActive) setOpen(true);
  }, [hasActive, plan.plan_id]);

  const toggle = (triggerEl: HTMLButtonElement) => {
    const scroller = findScrollParent(triggerEl);
    const prevTop = scroller?.scrollTop ?? 0;
    setOpen((v) => !v);
    requestAnimationFrame(() => {
      if (scroller) scroller.scrollTop = prevTop;
      setTimeout(() => {
        if (scroller) scroller.scrollTop = prevTop;
      }, 0);
    });
  };

  return (
    <ListCard className="my-1.5 overflow-hidden border-brand/20 bg-brand/[0.035] p-0 ring-1 ring-inset ring-brand/10">
      <div className="flex items-start gap-3 border-b border-brand/10 px-4 py-3">
        <ListTodo className="mt-0.5 size-4 shrink-0 text-brand" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-medium tracking-wide text-brand/90">任务进度</span>
            {hasActive ? (
              <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] font-medium text-brand">
                进行中
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 truncate text-sm font-medium text-foreground">{plan.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{planSummary(plan)}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={(e) => toggle(e.currentTarget)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="text-xs text-muted-foreground">步骤</span>
        <ChevronDown
          className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="border-t border-brand/10 px-4 py-3">
          <ol className="pl-1">
            {plan.steps.map((step, i) => (
              <TodoStepRow key={step.id} step={step} index={i} />
            ))}
          </ol>
        </div>
      ) : null}
    </ListCard>
  );
}
