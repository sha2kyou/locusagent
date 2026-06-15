import type { ChatPart } from "./model";

/** 当前 assistant 行在合并时间线中的起始下标（tool 轮次之后的新段落） */
export function streamingSegmentStart(parts: readonly ChatPart[]): number {
  let lastTool = -1;
  for (let i = 0; i < parts.length; i++) {
    if (parts[i].type === "tool") lastTool = i;
  }
  return lastTool + 1;
}

export interface StreamSyncSnapshot {
  reasoning_content?: string;
  content?: string;
}

/**
 * 将 active-run sync 快照合并进已有 parts，保留 tool 的时序位置。
 * 仅替换当前 assistant 段（末次 tool 块之后）的 thinking/text。
 */
export function mergeStreamSyncParts(
  parts: readonly ChatPart[],
  sync: StreamSyncSnapshot,
  opts: { live?: boolean } = {},
): ChatPart[] {
  const reasoning = (sync.reasoning_content || "").trim();
  const content = (sync.content || "").trim();
  if (!reasoning && !content) return [...parts];

  const start = streamingSegmentStart(parts);
  const prefix = parts.slice(0, start);
  const tail: ChatPart[] = [];
  if (reasoning) {
    tail.push({ type: "thinking", text: reasoning, completed: opts.live ? false : true });
  }
  if (content) tail.push({ type: "text", text: content });
  return [...prefix, ...tail];
}
