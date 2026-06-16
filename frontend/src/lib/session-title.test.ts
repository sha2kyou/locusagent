import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  displaySessionTitle,
  isBackendDefaultSessionTitle,
  BACKEND_DEFAULT_SESSION_TITLE,
} from "./session-title.ts";

describe("session-title", () => {
  const t = (key: string) => (key === "chat.session.defaultTitle" ? "New chat" : key);

  it("detects backend default title", () => {
    assert.equal(isBackendDefaultSessionTitle(BACKEND_DEFAULT_SESSION_TITLE), true);
    assert.equal(isBackendDefaultSessionTitle(""), true);
    assert.equal(isBackendDefaultSessionTitle("My topic"), false);
  });

  it("maps backend default to localized display", () => {
    assert.equal(displaySessionTitle(BACKEND_DEFAULT_SESSION_TITLE, t), "New chat");
    assert.equal(displaySessionTitle("My topic", t), "My topic");
  });
});
