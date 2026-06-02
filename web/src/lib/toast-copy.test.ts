import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { toastAction, truncateToastLabel } from "./toast-copy.ts";

describe("toast-copy", () => {
  it("truncates long labels", () => {
    const long = "a".repeat(60);
    assert.equal(truncateToastLabel(long).length, 48);
    assert.match(truncateToastLabel(long), /…$/);
  });

  it("formats delete with kind", () => {
    assert.equal(toastAction("已删除", "线性代数", "产物"), "已删除产物「线性代数」");
  });
});
