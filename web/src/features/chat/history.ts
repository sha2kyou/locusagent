import type { LegacyToolMeta, Message, OpenAIToolCall, ToolKind } from "@/api/types";
import { type ChatMessage, type ToolPart, uid } from "./model";

const PREVIEW_MAX = 1000;

function truncate(s: string): string {
  return s.length > PREVIEW_MAX ? s.slice(0, PREVIEW_MAX) : s;
}

function isOpenAIToolCall(tc: OpenAIToolCall | LegacyToolMeta): tc is OpenAIToolCall {
  return "function" in tc && !!(tc as OpenAIToolCall).function;
}

/**
 * 把后端历史消息（OpenAI 格式 assistant.tool_calls + role=tool 结果 + legacy 元数据）
 * 合并为前端时间线：相邻的 assistant/tool 行归入同一条 assistant 消息，按发生顺序保留 text/tool 块。
 */
export function coalesceHistory(items: Message[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  let cur: ChatMessage | null = null;

  const findTool = (id?: string | null): ToolPart | undefined => {
    if (!cur || !id) return undefined;
    for (let i = cur.parts.length - 1; i >= 0; i--) {
      const p = cur.parts[i];
      if (p.type === "tool" && p.id === id) return p;
    }
    return undefined;
  };

  for (const msg of items) {
    if (msg.role === "user") {
      if (cur) {
        result.push(cur);
        cur = null;
      }
      result.push({ id: uid("u"), role: "user", parts: [{ type: "text", text: msg.content || "" }] });
      continue;
    }
    if (msg.role === "system") continue;

    if (!cur) cur = { id: uid("a"), role: "assistant", parts: [] };

    if (msg.role === "assistant") {
      if (msg.content) cur.parts.push({ type: "text", text: msg.content });
      for (const tc of msg.tool_calls ?? []) {
        if (isOpenAIToolCall(tc)) {
          cur.parts.push({
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
      const preview = meta?.preview ?? truncate(msg.content || "");
      if (existing) {
        existing.running = false;
        existing.preview = preview;
        if (meta?.tool_name) existing.toolName = meta.tool_name;
        if (meta?.tool_kind) existing.toolKind = meta.tool_kind;
      } else {
        cur.parts.push({
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

  if (cur) result.push(cur);

  // 历史中残留的 running 工具一律置为完成（无 spinner）
  for (const m of result) {
    for (const p of m.parts) {
      if (p.type === "tool" && p.running) p.running = false;
    }
  }
  return result;
}
