import type { ThreadMessageLike } from "@assistant-ui/react";
import type { ChatMessage } from "./model";

type Part = Extract<ThreadMessageLike["content"], readonly unknown[]>[number];

/** 前端 ChatMessage → assistant-ui ThreadMessageLike（tool 元数据塞进 args.kind） */
export function convertMessage(message: ChatMessage): ThreadMessageLike {
  if (message.role === "user") {
    const text = message.parts.map((p) => (p.type === "text" ? p.text : "")).join("");
    return { role: "user", id: message.id, content: [{ type: "text", text }] };
  }

  const content: Part[] = [];
  for (const p of message.parts) {
    if (p.type === "text") {
      if (p.text) content.push({ type: "text", text: p.text });
    } else {
      content.push({
        type: "tool-call",
        toolCallId: p.id,
        toolName: p.toolName,
        argsText: "",
        args: { kind: p.toolKind, startedAt: p.startedAt },
        // result 存在即视为完成；running 时保持 undefined
        result: p.running ? undefined : (p.preview ?? ""),
      });
    }
  }
  if (message.error) {
    content.push({ type: "text", text: `\n\n> ⚠ ${message.error}` });
  }
  if (content.length === 0) content.push({ type: "text", text: "" });

  return { role: "assistant", id: message.id, content };
}
