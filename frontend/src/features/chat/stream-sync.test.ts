import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { mergeStreamSyncParts, streamingSegmentStart } from "./stream-sync.ts";
import type { ChatPart } from "./model.ts";

describe("streamingSegmentStart", () => {
  it("returns 0 when there are no tools", () => {
    const parts: ChatPart[] = [
      { type: "thinking", text: "a", completed: true },
      { type: "text", text: "hello" },
    ];
    assert.equal(streamingSegmentStart(parts), 0);
  });

  it("starts after the last completed tool block", () => {
    const parts: ChatPart[] = [
      { type: "thinking", text: "r1", completed: true },
      { type: "text", text: "before" },
      {
        type: "tool",
        id: "t1",
        toolName: "search",
        toolKind: "tool",
        running: false,
        startedAt: 0,
      },
      { type: "thinking", text: "r2", completed: false },
      { type: "text", text: "after" },
    ];
    assert.equal(streamingSegmentStart(parts), 3);
  });

  it("starts before a trailing running tool in the same round", () => {
    const parts: ChatPart[] = [
      { type: "thinking", text: "r1", completed: true },
      { type: "text", text: "before" },
      {
        type: "tool",
        id: "t1",
        toolName: "terminal",
        toolKind: "tool",
        running: true,
        startedAt: 0,
      },
    ];
    assert.equal(streamingSegmentStart(parts), 0);
  });
});

describe("mergeStreamSyncParts", () => {
  it("preserves tools before the streaming segment", () => {
    const parts: ChatPart[] = [
      { type: "thinking", text: "old-r1", completed: true },
      { type: "text", text: "old-text" },
      {
        type: "tool",
        id: "t1",
        toolName: "search",
        toolKind: "tool",
        running: false,
        startedAt: 0,
      },
      { type: "thinking", text: "stale", completed: false },
      { type: "text", text: "stale-tail" },
    ];
    const merged = mergeStreamSyncParts(
      parts,
      { reasoning_content: "fresh-r2", content: "fresh-text" },
      { live: true },
    );
    assert.deepEqual(merged, [
      { type: "thinking", text: "old-r1", completed: true },
      { type: "text", text: "old-text" },
      {
        type: "tool",
        id: "t1",
        toolName: "search",
        toolKind: "tool",
        running: false,
        startedAt: 0,
      },
      { type: "thinking", text: "fresh-r2", completed: false },
      { type: "text", text: "fresh-text" },
    ]);
  });

  it("replaces thinking/text before a trailing running tool", () => {
    const parts: ChatPart[] = [
      { type: "thinking", text: "stale-r", completed: true },
      { type: "text", text: "stale-text" },
      {
        type: "tool",
        id: "t1",
        toolName: "terminal",
        toolKind: "tool",
        running: true,
        startedAt: 0,
      },
    ];
    const merged = mergeStreamSyncParts(
      parts,
      { reasoning_content: "fresh-r", content: "fresh-text" },
      { live: true },
    );
    assert.deepEqual(merged, [
      { type: "thinking", text: "fresh-r", completed: false },
      { type: "text", text: "fresh-text" },
      {
        type: "tool",
        id: "t1",
        toolName: "terminal",
        toolKind: "tool",
        running: true,
        startedAt: 0,
      },
    ]);
  });

  it("leaves parts unchanged when sync is empty", () => {
    const parts: ChatPart[] = [{ type: "text", text: "keep" }];
    const merged = mergeStreamSyncParts(parts, {}, { live: true });
    assert.deepEqual(merged, parts);
  });
});
