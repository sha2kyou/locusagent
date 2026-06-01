import type { LegacyToolMeta, Message, OpenAIToolCall, ToolKind } from "@/api/types";
import { type ChatAttachment, type ChatMessage, type ToolPart, uid } from "./model";

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

/**
 * 把后端历史消息（OpenAI 格式 assistant.tool_calls + role=tool 结果 + legacy 元数据）
 * 合并为前端时间线：相邻的 assistant/tool 行归入同一条 assistant 消息，按发生顺序保留 text/tool 块。
 */
export function coalesceHistory(items: Message[]): ChatMessage[] {
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

  const startAssistant = () => {
    if (!cur) {
      cur = { id: uid("a"), role: "assistant", parts: [] };
      curArchived = false;
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
        archived: isArchived(msg),
        attachments: normalizeAttachments((msg as { attachments?: ChatAttachment[] }).attachments),
        parts: [{ type: "text", text: msg.content || "" }],
      });
      continue;
    }
    if (msg.role === "system") continue;

    startAssistant();
    if (isArchived(msg)) curArchived = true;

    if (msg.role === "assistant") {
      if (msg.content) cur!.parts.push({ type: "text", text: msg.content });
      for (const tc of msg.tool_calls ?? []) {
        if (isOpenAIToolCall(tc)) {
          cur!.parts.push({
            type: "tool",
            id: tc.id,
            toolName: tc.function.name,
            toolKind: "tool",
            running: true,
            startedAt: 0,
          });
        }
      }
    } else if (msg.role === "tool") {
      const meta = (msg.tool_calls?.[0] as LegacyToolMeta | undefined);
      const id = msg.tool_call_id ?? meta?.tool_call_id;
      const existing = findTool(id);
      const preview = meta?.preview ?? (msg.content || "");
      if (existing) {
        existing.running = false;
        existing.preview = preview;
        if (meta?.tool_name) existing.toolName = meta.tool_name;
        if (meta?.tool_kind) existing.toolKind = meta.tool_kind;
      } else {
        cur!.parts.push({
          type: "tool",
          id: id ?? uid("t"),
          toolName: meta?.tool_name ?? "tool",
          toolKind: (meta?.tool_kind ?? "tool") as ToolKind,
          running: false,
          preview,
          startedAt: 0,
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
  return result;
}
