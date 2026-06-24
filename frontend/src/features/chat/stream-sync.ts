import type { ChatPart } from "./model";

/** 末尾连续 running tool 的起止下标；无则 null */
function trailingRunningToolRange(parts: readonly ChatPart[]): { start: number; end: number } | null {
  let i = parts.length - 1;
  while (i >= 0 && parts[i].type === "tool" && parts[i].running) {
    i -= 1;
  }
  const start = i + 1;
  if (start >= parts.length) return null;
  return { start, end: parts.length };
}

/** 当前 assistant 行在合并时间线中的起始下标（tool 轮次之后的新段落） */
export function streamingSegmentStart(parts: readonly ChatPart[]): number {
  const trailing = trailingRunningToolRange(parts);
  if (trailing) {
    let prevTool = -1;
    for (let i = 0; i < trailing.start; i++) {
      if (parts[i].type === "tool") prevTool = i;
    }
    return prevTool + 1;
  }
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
 * 已完成 tool 之后：替换末段 thinking/text（新一轮流式）。
 * 末尾仍有 running tool：替换该 tool 同轮次的 thinking/text，保留 running tool。
 */
export function mergeStreamSyncParts(
  parts: readonly ChatPart[],
  sync: StreamSyncSnapshot,
  opts: { live?: boolean } = {},
): ChatPart[] {
  const reasoning = (sync.reasoning_content || "").trim();
  const content = (sync.content || "").trim();
  if (!reasoning && !content) return [...parts];

  const tail: ChatPart[] = [];
  if (reasoning) {
    tail.push({ type: "thinking", text: reasoning, completed: opts.live ? false : true });
  }
  if (content) tail.push({ type: "text", text: content });

  const trailing = trailingRunningToolRange(parts);
  if (trailing) {
    const segmentStart = streamingSegmentStart(parts);
    const prefix = parts.slice(0, segmentStart);
    const suffix = parts.slice(trailing.start);
    return [...prefix, ...tail, ...suffix];
  }

  const start = streamingSegmentStart(parts);
  const prefix = parts.slice(0, start);
  return [...prefix, ...tail];
}
