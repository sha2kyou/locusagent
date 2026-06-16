import { describe, it, before } from "node:test";
import assert from "node:assert/strict";
import { ensureI18nReady } from "../i18n/index.ts";
import i18n from "../i18n/index.ts";
import { resolveAppTimeZone, sessionListGroupLabel } from "./format-time.ts";

before(async () => {
  await ensureI18nReady();
  await i18n.changeLanguage("zh");
});

describe("resolveAppTimeZone", () => {
  it("returns UTC for empty or invalid zones", () => {
    assert.equal(resolveAppTimeZone(""), "UTC");
    assert.equal(resolveAppTimeZone("Not/AZone"), "UTC");
  });

  it("keeps valid IANA zones", () => {
    assert.equal(resolveAppTimeZone("Asia/Shanghai"), "Asia/Shanghai");
  });
});

describe("sessionListGroupLabel", () => {
  it("uses configured timezone for today boundary", () => {
    const now = new Date("2026-06-16T08:00:00Z");
    const iso = "2026-06-15T20:00:00Z";
    assert.equal(sessionListGroupLabel(iso, "Asia/Shanghai", now), "今天");
    assert.equal(sessionListGroupLabel(iso, "UTC", now), "昨天");
  });
});
