import type { LegacyToolMeta, Message, OpenAIToolCall, ToolKind } from "@/api/types";
import { type ChatAttachment, type ChatMessage, type ToolPart, uid } from "./model";
import { formatToolArgsPreview } from "./tool-args";

function isOpenAIToolCall(tc: OpenAIToolCall | LegacyToolMeta | Record<string, unknown>): tc is OpenAIToolCall {
  return "function" in tc && !!(tc as OpenAIToolCall).function;
}

function isArchived(msg: Message): boolean {
  return msg.context_state === "archived";
}

function compressionMeta(msg: Message): Record<string, unknown> | undefined {
  const raw = msg.tool_calls;
  if (!raw) return undefined;
  if (Array.isArray(raw)) {
    return (raw[0] as { compression?: Record<string, unknown> } | undefined)?.compression;
  }
  if (typeof raw === "object" && "compression" in raw) {
    return (raw as { compression?: Record<string, unknown> }).compression;
  }
  return undefined;
}

function compressionPreview(msg: Message): string {
  const meta = compressionMeta(msg);
  const mode = String(meta?.mode ?? "distill");
  const before = Number(meta?.before_tokens ?? 0);
  const after = Number(meta?.after_tokens ?? 0);
  const body = (msg.content || "").trim();
  const header = `【自动上下文压缩】mode=${mode}, tokens: ${before} -> ${after}`;
  return body ? `${header}\n\n${body}` : `${header}\n本次未生成可展示摘要（已进行截断保留）。`;
}

/** 去掉入库用的附件元数据行，气泡只展示用户正文（附件由芯片展示）。 */
export function userMessageDisplayText(content: string): string {
  const lines = (content || "").split("\n");
  const kept = lines.filter((line) => {
    const t = line.trim();
    if (!t) return false;
    if (t === "[attachment]") return false;
    if (t.startsWith("[attachment_ids:")) return false;
    if (t.startsWith("[用户附件]")) return false;
    return true;
  });
  return kept.join("\n").trim();
}

function normalizeAttachments(
  fromApi?: {
    id: string;
    name: string;
    kind: "text" | "image" | "other";
    mimeType?: string;
    text?: string;
    imageDataUrl?: string;
    processable: boolean;
    unsupportedReason?: string;
    truncated?: boolean;
  }[],
): ChatAttachment[] | undefined {
  if (!fromApi || fromApi.length === 0) return undefined;
  return fromApi.map((a) => ({
    id: a.id,
    name: a.name,
    kind: a.kind,
    mimeType: a.mimeType,
    text: a.text,
    imageDataUrl: a.imageDataUrl,
    processable: a.processable,
    unsupportedReason: a.unsupportedReason,
    truncated: a.truncated,
  }));
}

function flushAssistant(result: ChatMessage[], cur: ChatMessage | null, curArchived: boolean) {
  if (!cur) return;
  if (curArchived) cur.archived = true;
  result.push(cur);
}

export interface CoalesceHistoryOptions {
  /** 会话仍有 active run：最后一条 assistant 的末段 thinking 保持未完成态 */
  live?: boolean;
}

/** 供 active-run 轮询判断消息是否有变化 */
export function historyPollKey(items: Message[]): string {
  const tail = items.slice(-4);
  return tail
    .map(
      (m) =>
        `${m.id}:${m.role}:${(m.content || "").length}:${(m.reasoning_content || "").length}:${Array.isArray(m.tool_calls) ? m.tool_calls.length : 0}:${m.tool_call_id ?? ""}`,
    )
    .join("|");
}

/** active run 重连时，仅当末段 part 为 thinking 才标记为进行中 */
function applyLiveThinkingState(messages: ChatMessage[]): ChatMessage[] {
  if (messages.length === 0) return messages;
  const last = messages[messages.length - 1];
  if (last.role !== "assistant" || last.parts.length === 0) return messages;
  const lastIdx = last.parts.length - 1;
  const lastPart = last.parts[lastIdx];
  if (lastPart.type !== "thinking") return messages;
  const parts = last.parts.map((p, i) =>
    i === lastIdx && p.type === "thinking" ? { ...p, completed: false } : p,
  );
  return [...messages.slice(0, -1), { ...last, parts }];
}

/**
 * 把后端历史消息（OpenAI 格式 assistant.tool_calls + role=tool 结果 + legacy 元数据）
 * 合并为前端时间线：相邻的 assistant/tool 行归入同一条 assistant 消息，按发生顺序保留 text/tool 块。
 */
export function coalesceHistory(items: Message[], opts: CoalesceHistoryOptions = {}): ChatMessage[] {
  const result: ChatMessage[] = [];
  let cur: ChatMessage | null = null;
  let curArchived = false;

  const findTool = (id?: string | null): ToolPart | undefined => {
    if (!cur || !id) return undefined;
    for (let i = cur.parts.length - 1; i >= 0; i--) {
      const p = cur.parts[i];
      if (p.type === "tool" && p.id === id) return p;
    }
    return undefined;
  };

  const startAssistant = (createdAt?: string) => {
    if (!cur) {
      cur = {
        id: uid("a"),
        role: "assistant",
        parts: [],
        ...(createdAt ? { createdAt } : {}),
      };
      curArchived = false;
    } else if (!cur.createdAt && createdAt) {
      cur.createdAt = createdAt;
    }
  };

  for (const msg of items) {
    if (msg.role === "context_summary") {
      flushAssistant(result, cur, curArchived);
      cur = null;
      curArchived = false;
      result.push({
        id: uid("a"),
        role: "assistant",
        createdAt: msg.created_at,
        parts: [
          {
            type: "tool",
            id: uid("t"),
            toolName: "summarize",
            toolKind: "tool",
            running: false,
            preview: compressionPreview(msg),
            startedAt: 0,
          },
        ],
      });
      continue;
    }

    if (msg.role === "user") {
      flushAssistant(result, cur, curArchived);
      cur = null;
      curArchived = false;
      result.push({
        id: uid("u"),
        role: "user",
        createdAt: msg.created_at,
        archived: isArchived(msg),
        attachments: normalizeAttachments((msg as { attachments?: ChatAttachment[] }).attachments),
        parts: [{ type: "text", text: userMessageDisplayText(msg.content || "") }],
      });
      continue;
    }
    if (msg.role === "system") continue;

    startAssistant(msg.created_at);
    if (isArchived(msg)) curArchived = true;

    if (msg.role === "assistant") {
      const reasoning = (msg.reasoning_content || "").trim();
      const content = (msg.content || "").trim();
      const toolCalls = (msg.tool_calls ?? []).filter(isOpenAIToolCall);
      // 与流式顺序一致：reasoning → content → tool_calls（同轮 completion 内 content 先于 tool）
      if (reasoning) cur!.parts.push({ type: "thinking", text: reasoning, completed: true });
      if (content) cur!.parts.push({ type: "text", text: content });
      for (const tc of toolCalls) {
        cur!.parts.push({
          type: "tool",
          id: tc.id,
          toolName: tc.function.name,
          toolKind: "tool",
          running: true,
          startedAt: 0,
          argsPreview: formatToolArgsPreview(tc.function.arguments),
        });
      }
      const atts = normalizeAttachments(msg.attachments);
      if (atts?.length) {
        cur!.attachments = [...(cur!.attachments ?? []), ...atts];
      }
    } else if (msg.role === "tool") {
      const meta = (msg.tool_calls?.[0] as LegacyToolMeta | undefined);
      const id = msg.tool_call_id ?? meta?.tool_call_id;
      const existing = findTool(id);
      const preview = meta?.preview ?? (msg.content || "");
      const elapsedMs =
        typeof meta?.elapsed_ms === "number" && meta.elapsed_ms >= 0 ? meta.elapsed_ms : undefined;
      if (existing) {
        existing.running = false;
        existing.preview = preview;
        if (meta?.tool_name) existing.toolName = meta.tool_name;
        if (meta?.tool_kind) existing.toolKind = meta.tool_kind;
        if (elapsedMs !== undefined) existing.elapsedMs = elapsedMs;
      } else {
        cur!.parts.push({
          type: "tool",
          id: id ?? uid("t"),
          toolName: meta?.tool_name ?? "tool",
          toolKind: (meta?.tool_kind ?? "tool") as ToolKind,
          running: false,
          preview,
          startedAt: 0,
          ...(elapsedMs !== undefined ? { elapsedMs } : {}),
        });
      }
    }
  }

  flushAssistant(result, cur, curArchived);

  for (const m of result) {
    for (const p of m.parts) {
      if (p.type === "tool" && p.running) p.running = false;
    }
  }
  return opts.live ? applyLiveThinkingState(result) : result;
}
