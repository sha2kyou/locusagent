import { useEffect, useMemo, useState } from "react";
import { useMessage, type ToolCallMessagePartComponent } from "@assistant-ui/react";
import { Blocks, Brain, ChevronDown, HelpCircle, Loader2, Send, Sparkles, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import { findScrollParent } from "@/lib/scroll-parent";
import { usePinnedCollapse } from "@/lib/use-pinned-collapse";
import { useImeEnterGuard } from "@/lib/ime-enter";
import { Button } from "@/components/ui/button";
import { ListCard } from "@/components/ui/panel";
import type { ToolKind } from "@/api/types";
import { useChat } from "./ChatProvider";
import type { ChatMessage, ChatPart, ToolPart } from "./model";
import { isTodoTool, parseTodoPlan } from "./todo";

function isRenderableGenericTool(part: ChatPart): part is ToolPart {
  if (part.type !== "tool") return false;
  if (isClarifyTool(part.toolName) && !part.running && parseClarify(part.preview)) return false;
  if (isTodoTool(part.toolName) && !part.running && parseTodoPlan(part.preview)) return false;
  return true;
}

function findLastGenericToolId(messages: ChatMessage[]): string | null {
  let lastId: string | null = null;
  for (const msg of messages) {
    if (msg.role !== "assistant") continue;
    for (const p of msg.parts) {
      if (isRenderableGenericTool(p)) lastId = p.id;
    }
  }
  return lastId;
}

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
    const data = JSON.parse(raw) as Partial<ClarifyPayload>;
    if (!data || typeof data.question !== "string") return null;
    const rawChoices = Array.isArray(data.choices) ? data.choices : [];
    const choices = rawChoices.map((o) => String(o).trim()).filter(Boolean).slice(0, 4);
    if (choices.length < 2) return null;
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
  return `问题：${question}\n回答：${answer}`;
}

function ClarifyCard({ payload }: { payload: ClarifyPayload }) {
  const { send, isRunning } = useChat();
  const { isLast } = useMessage();
  const { onCompositionStart, onCompositionEnd, shouldBlockEnter } = useImeEnterGuard();
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
      {payload.allow_other && (
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
            onCompositionStart={onCompositionStart}
            onCompositionEnd={onCompositionEnd}
            onKeyDown={(e) => {
              if (shouldBlockEnter(e)) e.preventDefault();
            }}
            placeholder="其他（自由输入）…"
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

function isClarifyTool(toolName: string): boolean {
  return toolName === "clarify" || toolName.endsWith("/clarify");
}

export const ToolEvent: ToolCallMessagePartComponent = (props) => {
  if (isClarifyTool(props.toolName)) {
    const payload = parseClarify(props.result);
    if (payload) return <ClarifyCard payload={payload} />;
  }
  return <GenericToolBlock blockId={props.toolCallId} toolName={props.toolName} args={props.args} result={props.result} status={props.status} />;
};

/** 按 ChatPart 时间线直接渲染工具块（不依赖 MessagePrimitive.Parts 顺序） */
export function ToolPartView({ part }: { part: ToolPart }) {
  if (isClarifyTool(part.toolName)) {
    if (!part.running) {
      const payload = parseClarify(part.preview);
      if (payload) return <ClarifyCard payload={payload} />;
    }
  }
  if (isTodoTool(part.toolName) && !part.running && parseTodoPlan(part.preview)) {
    return null;
  }
  const running = part.running;
  return (
    <GenericToolBlock
      key={part.id}
      blockId={part.id}
      toolName={part.toolName}
      args={{ kind: part.toolKind, startedAt: part.startedAt }}
      result={running ? undefined : (part.preview ?? "")}
      status={{ type: running ? "running" : "complete" }}
    />
  );
}

type ToolBlockStatus = { type?: string } | undefined;

function GenericToolBlock({
  blockId,
  toolName,
  args,
  result,
  status,
}: {
  blockId: string;
  toolName: string;
  args: unknown;
  result: unknown;
  status?: ToolBlockStatus;
}) {
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

  const { messages } = useChat();
  const lastGenericToolId = useMemo(() => findLastGenericToolId(messages), [messages]);
  const preview = typeof result === "string" ? result : result ? JSON.stringify(result) : "";
  const elapsed = startedAt ? fmtElapsed((running ? now : Date.now()) - startedAt) : null;
  const hasResult = preview.trim().length > 0;
  const defaultExpanded = blockId === lastGenericToolId;
  const [open, toggleOpen] = usePinnedCollapse(blockId, defaultExpanded);

  const toggleResult = (triggerEl: HTMLButtonElement) => {
    const scroller = findScrollParent(triggerEl);
    const prevTop = scroller?.scrollTop ?? 0;
    toggleOpen();
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
      <div className="flex items-center gap-3 px-3.5 py-2.5">
        <span
          className={cn(
            "flex size-6 shrink-0 items-center justify-center rounded-md",
            running
              ? "bg-brand/10 text-brand"
              : "bg-muted text-muted-foreground",
          )}
        >
          {running ? <Loader2 className="size-3.5 animate-spin" /> : <Icon className="size-3.5" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[13px] font-medium text-foreground">{toolName}</span>
            {running && (
              <span className="shrink-0 rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] font-medium text-brand">
                执行中
              </span>
            )}
          </div>
        </div>
        {elapsed && (
          <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">
            {elapsed}
          </span>
        )}
      </div>
      {!running && hasResult ? (
        <>
          <button
            type="button"
            onClick={(e) => toggleResult(e.currentTarget)}
            className="flex w-full items-center justify-between border-t border-border px-3.5 py-2 text-left transition-colors hover:bg-surface/60"
          >
            <span className="text-xs text-muted-foreground">查看结果</span>
            <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform duration-150", open && "rotate-180")} />
          </button>
          {open ? (
            <div className="border-t border-border bg-surface/30 px-3.5 py-3">
              <pre className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-foreground/80">{preview}</pre>
            </div>
          ) : null}
        </>
      ) : null}
    </ListCard>
  );
}
