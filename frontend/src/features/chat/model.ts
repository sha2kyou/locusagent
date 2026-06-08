import type { ToolKind } from "@/api/types";

export interface ToolPart {
  type: "tool";
  id: string;
  toolName: string;
  toolKind: ToolKind;
  running: boolean;
  preview?: string;
  argsPreview?: string;
  startedAt: number;
  elapsedMs?: number;
}

export interface TextPart {
  type: "text";
  text: string;
}

export interface ThinkingPart {
  type: "thinking";
  text: string;
  /** 该段思考已结束（后续出现工具/文本/新思考段） */
  completed?: boolean;
}

export type ChatPart = TextPart | ThinkingPart | ToolPart;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  parts: ChatPart[];
  /** ISO 8601，消息开始时间（用户发送 / 助手回合首条入库时间） */
  createdAt?: string;
  sourceText?: string;
  attachments?: ChatAttachment[];
  error?: string;
  archived?: boolean;
}

export interface ChatAttachment {
  id: string;
  name: string;
  kind: "text" | "image" | "other";
  mimeType?: string;
  text?: string;
  imageDataUrl?: string;
  processable: boolean;
  unsupportedReason?: string;
  truncated?: boolean;
}

let counter = 0;
export function uid(prefix = "m"): string {
  counter += 1;
  return `${prefix}_${Date.now().toString(36)}_${counter}`;
}

export function userMessage(
  text: string,
  sourceText?: string,
  attachments?: ChatAttachment[],
): ChatMessage {
  return {
    id: uid("u"),
    role: "user",
    parts: [{ type: "text", text }],
    createdAt: new Date().toISOString(),
    sourceText,
    attachments: attachments?.length ? attachments : undefined,
  };
}

export function emptyAssistant(): ChatMessage {
  return { id: uid("a"), role: "assistant", parts: [], createdAt: new Date().toISOString() };
}

/** 将尚未结束的 thinking 段全部标记为已完成 */
export function completeThinkingParts(parts: ChatPart[]): ChatPart[] {
  return parts.map((p) =>
    p.type === "thinking" && !p.completed ? { ...p, completed: true } : p,
  );
}

/** 把文本增量追加到末尾文本块（无则新建） */
export function appendText(parts: ChatPart[], delta: string): ChatPart[] {
  const last = parts[parts.length - 1];
  let base = parts;
  if (last?.type === "thinking") {
    base = [...parts.slice(0, -1), { ...last, completed: true }];
  }
  const tail = base[base.length - 1];
  if (tail && tail.type === "text") {
    return [...base.slice(0, -1), { type: "text", text: tail.text + delta }];
  }
  return [...base, { type: "text", text: delta }];
}

/** 思考链增量：合并到末尾未完成的 thinking 块 */
export function appendThinking(parts: ChatPart[], delta: string): ChatPart[] {
  const last = parts[parts.length - 1];
  if (last?.type === "thinking" && !last.completed) {
    return [...parts.slice(0, -1), { type: "thinking", text: last.text + delta }];
  }
  return [...parts, { type: "thinking", text: delta }];
}
