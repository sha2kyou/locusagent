import { useEffect, useState } from "react";
import { useMessage, type ToolCallMessagePartComponent } from "@assistant-ui/react";
import { Blocks, Brain, ChevronDown, HelpCircle, Loader2, Send, Sparkles, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ListCard } from "@/components/ui/panel";
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
  const hasResult = preview.trim().length > 0;
  const [open, setOpen] = useState(false);

  const toggleResult = (triggerEl: HTMLButtonElement) => {
    const scroller = findScrollParent(triggerEl);
    const prevTop = scroller?.scrollTop ?? 0;
    setOpen((v) => !v);
    // assistant-ui 在消息尺寸变化时可能触发自动跟随到底部，这里强制恢复用户当前阅读位置。
    requestAnimationFrame(() => {
      if (scroller) scroller.scrollTop = prevTop;
      setTimeout(() => {
        if (scroller) scroller.scrollTop = prevTop;
      }, 0);
    });
  };

  return (
    <ListCard className="my-1.5 overflow-hidden p-0">
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={cn("shrink-0", running ? "text-brand" : "text-muted-foreground")}>
              {running ? <Loader2 className="size-4 animate-spin" /> : <Icon className="size-4" />}
            </span>
            <span className="truncate font-medium text-foreground">{toolName}</span>
            {running ? <span className="text-sm text-muted-foreground">执行中…</span> : null}
          </div>
        </div>
        {elapsed && <span className="shrink-0 text-xs text-muted-foreground/70">{elapsed}</span>}
      </div>
      {!running && hasResult ? (
        <>
          <button
            type="button"
            onClick={(e) => toggleResult(e.currentTarget)}
            className="flex w-full items-center justify-between border-t border-border px-4 py-2.5 text-left"
          >
            <span className="text-xs text-muted-foreground">结果</span>
            <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
          </button>
          {open ? (
            <div className="border-t border-border px-4 py-3">
              <pre className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap text-sm text-foreground">{preview}</pre>
            </div>
          ) : null}
        </>
      ) : null}
    </ListCard>
  );
};

function findScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = el;
  while (node) {
    const style = window.getComputedStyle(node);
    const overflowY = style.overflowY;
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}
