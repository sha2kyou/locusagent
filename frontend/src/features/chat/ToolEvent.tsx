import { useEffect, useState } from "react";
import { useMessage, type ToolCallMessagePartComponent } from "@assistant-ui/react";
import { Blocks, Brain, HelpCircle, Send, Sparkles, Wrench } from "lucide-react";
import { CollapsibleMetaBlock } from "./CollapsibleMetaBlock";
import { useImeEnterGuard } from "@/lib/ime-enter";
import { Button } from "@/components/ui/button";
import type { ToolKind } from "@/api/types";
import { useChat } from "./ChatProvider";
import type { ToolPart } from "./model";
import { formatToolArgsPreview } from "./tool-args";
import { isTodoTool, parseTodoPlan } from "./todo";

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

function resolveElapsedLabel(opts: {
  startedAt?: number;
  elapsedMs?: number;
  running: boolean;
  now: number;
}): string | null {
  const { startedAt, elapsedMs, running, now } = opts;
  if (!running) {
    if (typeof elapsedMs === "number" && elapsedMs >= 0) {
      return fmtElapsed(elapsedMs);
    }
    return null;
  }
  if (startedAt) {
    return fmtElapsed(now - startedAt);
  }
  return null;
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
  return <GenericToolBlock blockId={props.toolCallId} toolName={props.toolName} args={props.args} argsPreview={resolveArgsPreviewFromProps(props.args)} result={props.result} status={props.status} />;
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
      args={{ kind: part.toolKind, startedAt: part.startedAt, elapsedMs: part.elapsedMs }}
      argsPreview={part.argsPreview}
      result={running ? undefined : (part.preview ?? "")}
      status={{ type: running ? "running" : "complete" }}
    />
  );
}

type ToolBlockStatus = { type?: string } | undefined;

function resolveArgsPreviewFromProps(args: unknown): string | undefined {
  if (!args || typeof args !== "object") return undefined;
  const row = args as Record<string, unknown>;
  if (typeof row.argsPreview === "string" && row.argsPreview.trim()) return row.argsPreview.trim();
  const rest = { ...row };
  delete rest.kind;
  delete rest.startedAt;
  delete rest.elapsedMs;
  delete rest.argsPreview;
  if (Object.keys(rest).length === 0) return undefined;
  return formatToolArgsPreview(JSON.stringify(rest));
}

function GenericToolBlock({
  blockId,
  toolName,
  args,
  argsPreview,
  result,
  status,
}: {
  blockId: string;
  toolName: string;
  args: unknown;
  argsPreview?: string;
  result: unknown;
  status?: ToolBlockStatus;
}) {
  const argRow = args as { kind?: ToolKind; startedAt?: number; elapsedMs?: number };
  const kind = (argRow.kind ?? "tool") as ToolKind;
  const startedAt = argRow.startedAt ?? 0;
  const elapsedMs = argRow.elapsedMs;
  const running = status?.type === "running" || status?.type === "requires-action";
  const Icon = KIND_ICON[kind] ?? Wrench;

  const [now, setNow] = useState(Date.now());
  const [frozenElapsedMs, setFrozenElapsedMs] = useState<number | undefined>(undefined);
  useEffect(() => {
    if (!running || !startedAt) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [running, startedAt]);

  useEffect(() => {
    if (running) {
      setFrozenElapsedMs(undefined);
      return;
    }
    if (typeof elapsedMs === "number" && elapsedMs >= 0) {
      setFrozenElapsedMs(elapsedMs);
      return;
    }
    if (startedAt) {
      setFrozenElapsedMs(Math.max(0, Date.now() - startedAt));
    }
  }, [running, elapsedMs, startedAt]);

  const preview = typeof result === "string" ? result : result ? JSON.stringify(result) : "";
  const elapsed = resolveElapsedLabel({
    startedAt,
    elapsedMs: running ? elapsedMs : (frozenElapsedMs ?? elapsedMs),
    running,
    now,
  });
  const hasResult = preview.trim().length > 0;
  const paramPreview = argsPreview ?? resolveArgsPreviewFromProps(args);

  return (
    <CollapsibleMetaBlock
      blockId={blockId}
      active={running}
      title={toolName}
      running={running}
      showRunningBadge
      icon={<Icon className="size-3.5" />}
      preview={paramPreview}
      hidePreviewWhenOpen={false}
      trailing={
        elapsed ? (
          <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">
            {elapsed}
          </span>
        ) : undefined
      }
    >
      {!running && hasResult ? (
        <pre className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-foreground/80">
          {preview}
        </pre>
      ) : undefined}
    </CollapsibleMetaBlock>
  );
}
