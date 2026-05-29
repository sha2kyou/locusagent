import type { ToolKind } from "@/api/types";

export interface ToolPart {
  type: "tool";
  id: string;
  toolName: string;
  toolKind: ToolKind;
  running: boolean;
  preview?: string;
  startedAt: number;
  elapsedMs?: number;
}

export interface TextPart {
  type: "text";
  text: string;
}

export type ChatPart = TextPart | ToolPart;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  parts: ChatPart[];
  error?: string;
}

let counter = 0;
export function uid(prefix = "m"): string {
  counter += 1;
  return `${prefix}_${Date.now().toString(36)}_${counter}`;
}

export function userMessage(text: string): ChatMessage {
  return { id: uid("u"), role: "user", parts: [{ type: "text", text }] };
}

export function emptyAssistant(): ChatMessage {
  return { id: uid("a"), role: "assistant", parts: [] };
}

/** 把文本增量追加到末尾文本块（无则新建） */
export function appendText(parts: ChatPart[], delta: string): ChatPart[] {
  const last = parts[parts.length - 1];
  if (last && last.type === "text") {
    return [...parts.slice(0, -1), { type: "text", text: last.text + delta }];
  }
  return [...parts, { type: "text", text: delta }];
}
