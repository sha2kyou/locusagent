import { useEffect, useState } from "react";
import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { Blocks, Brain, ChevronRight, Loader2, Sparkles, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolKind } from "@/api/types";

const KIND_ICON = {
  skill: Sparkles,
  mcp: Blocks,
  memory: Brain,
  tool: Wrench,
} as const;

function fmtElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export const ToolEvent: ToolCallMessagePartComponent = ({ toolName, args, result, status }) => {
  const kind = ((args as { kind?: ToolKind })?.kind ?? "tool") as ToolKind;
  const startedAt = (args as { startedAt?: number })?.startedAt ?? 0;
  const running = status?.type === "running" || status?.type === "requires-action";
  const Icon = KIND_ICON[kind] ?? Wrench;

  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running || !startedAt) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [running, startedAt]);

  const preview = typeof result === "string" ? result : result ? JSON.stringify(result) : "";
  const elapsed = startedAt ? fmtElapsed((running ? now : Date.now()) - startedAt) : null;
  const [open, setOpen] = useState(false);
  const long = preview.length > 120;

  return (
    <div className="my-1.5 flex items-start gap-2 rounded-lg border border-border bg-surface/40 px-3 py-2 text-[13px]">
      <span className={cn("mt-0.5 shrink-0", running ? "text-brand" : "text-muted-foreground")}>
        {running ? <Loader2 className="size-4 animate-spin" /> : <Icon className="size-4" />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-foreground">{toolName}</span>
          {running ? (
            <span className="text-muted-foreground">执行中…</span>
          ) : (
            preview && !long && <span className="truncate text-muted-foreground">{preview}</span>
          )}
          {elapsed && <span className="ml-auto shrink-0 text-xs text-muted-foreground/70">{elapsed}</span>}
        </div>
        {!running && long && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="mt-1 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} />
            {open ? "收起" : "查看结果"}
          </button>
        )}
        {!running && long && open && (
          <pre className="mt-1.5 max-h-72 overflow-auto rounded-md border border-border bg-surface-2 p-2 text-xs text-muted-foreground">
            {preview}
          </pre>
        )}
      </div>
    </div>
  );
};
