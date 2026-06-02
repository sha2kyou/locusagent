import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { toastMessageForNotification } from "./notification-copy.ts";
import type { NotificationEntry } from "@/api/types";

function item(partial: Partial<NotificationEntry> & Pick<NotificationEntry, "title">): NotificationEntry {
  return {
    id: 1,
    kind: "success",
    category: null,
    body: "",
    link: null,
    read: false,
    created_at: null,
    ...partial,
  };
}

describe("toastMessageForNotification", () => {
  it("formats artifact save with category", () => {
    assert.equal(
      toastMessageForNotification(
        item({ title: "线性代数公式", category: "保存产物（数学）" }),
      ),
      "产物已保存：线性代数公式（数学）",
    );
  });

  it("keeps legacy prefixed title", () => {
    assert.equal(
      toastMessageForNotification(item({ title: "产物已保存：旧格式" })),
      "产物已保存：旧格式",
    );
  });

  it("passes through other notifications", () => {
    assert.equal(
      toastMessageForNotification(item({ title: "定时任务已完成", category: "定时任务" })),
      "定时任务已完成",
    );
  });
});
