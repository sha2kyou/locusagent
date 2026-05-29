import { useEffect, useState } from "react";
import { useMessage, type ToolCallMessagePartComponent } from "@assistant-ui/react";
import { Blocks, Brain, ChevronRight, HelpCircle, Loader2, Send, Sparkles, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { ToolKind } from "@/api/types";
import { useChat } from "./ChatProvider";

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

interface ClarifyPayload {
  question: string;
  choices: string[];
  allow_other?: boolean;
}

function parseClarify(result: unknown): ClarifyPayload | null {
  const raw = typeof result === "string" ? result : "";
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as Partial<ClarifyPayload> & { options?: unknown };
    if (!data || typeof data.question !== "string") return null;
    const rawChoices = Array.isArray(data.choices)
      ? data.choices
      : Array.isArray(data.options)
        ? data.options
        : [];
    const choices = rawChoices.map((o) => String(o).trim()).filter(Boolean).slice(0, 4);
    return {
      question: data.question,
      choices,
      allow_other: data.allow_other !== false,
    };
  } catch {
    /* 非法 JSON：回退为普通工具展示 */
  }
  return null;
}

function clarifyMessage(question: string, answer: string): string {
  return `针对问题「${question}」，我的回答：${answer}`;
}

function ClarifyCard({ payload }: { payload: ClarifyPayload }) {
  const { send, isRunning } = useChat();
  const { isLast } = useMessage();
  const [picked, setPicked] = useState(false);
  const [other, setOther] = useState("");
  // 已选过、正在生成、或该卡片已非最后一条消息（含刷新后的历史）→ 不可再选
  const disabled = isRunning || picked || !isLast;
  const pick = (answer: string) => {
    const t = answer.trim();
    if (!t || disabled) return;
    setPicked(true);
    send(clarifyMessage(payload.question, t));
  };
  return (
    <div className="my-1.5 rounded-lg border border-border bg-surface/40 px-3 py-2.5 text-[13px]">
      <div className="flex items-start gap-2">
        <HelpCircle className="mt-0.5 size-4 shrink-0 text-brand" />
        <span className="font-medium text-foreground">{payload.question}</span>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {payload.choices.map((opt, i) => (
          <Button
            key={`${i}-${opt}`}
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => pick(opt)}
          >
            {opt}
          </Button>
        ))}
      </div>
      {(payload.allow_other || payload.choices.length === 0) && (
        <form
          className="mt-2 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            pick(other);
            setOther("");
          }}
        >
          <input
            value={other}
            onChange={(e) => setOther(e.target.value)}
            placeholder={payload.choices.length === 0 ? "请输入你的回答…" : "其他（自由输入）…"}
            disabled={disabled}
            className="h-8 min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 text-[13px] text-foreground outline-none placeholder:text-muted-foreground/70 focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-45"
          />
          <Button type="submit" variant="ghost" size="icon-sm" disabled={disabled || !other.trim()}>
            <Send className="size-4" />
          </Button>
        </form>
      )}
    </div>
  );
}

export const ToolEvent: ToolCallMessagePartComponent = (props) => {
  if (props.toolName === "clarify") {
    const payload = parseClarify(props.result);
    if (payload) return <ClarifyCard payload={payload} />;
  }
  return <GenericToolEvent {...props} />;
};

const GenericToolEvent: ToolCallMessagePartComponent = ({ toolName, args, result, status }) => {
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
