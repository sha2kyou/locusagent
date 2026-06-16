import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

import { ensureI18nReady } from "../i18n/index.ts";
import i18n from "../i18n/index.ts";
import { toastAction, truncateToastLabel } from "./toast-copy.ts";

before(async () => {
  await ensureI18nReady();
  await i18n.changeLanguage("zh");
});

describe("toast-copy", () => {
  it("truncates long labels", () => {
    const long = "a".repeat(60);
    assert.equal(truncateToastLabel(long).length, 48);
    assert.match(truncateToastLabel(long), /…$/);
  });

  it("formats delete with kind", () => {
    assert.equal(toastAction("deleted", "线性代数", "artifact"), "已删除产物「线性代数」");
  });
});
