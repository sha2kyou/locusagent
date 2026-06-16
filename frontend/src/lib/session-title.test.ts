import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  displaySessionTitle,
  isBackendDefaultSessionTitle,
  BACKEND_DEFAULT_SESSION_TITLES,
} from "./session-title.ts";

describe("session-title", () => {
  const t = (key: string) => (key === "chat.session.defaultTitle" ? "New chat" : key);

  it("detects backend default titles for zh and en", () => {
    for (const title of BACKEND_DEFAULT_SESSION_TITLES) {
      assert.equal(isBackendDefaultSessionTitle(title), true);
    }
    assert.equal(isBackendDefaultSessionTitle(""), true);
    assert.equal(isBackendDefaultSessionTitle("My topic"), false);
  });

  it("maps backend default to localized display", () => {
    for (const title of BACKEND_DEFAULT_SESSION_TITLES) {
      assert.equal(displaySessionTitle(title, t), "New chat");
    }
    assert.equal(displaySessionTitle("My topic", t), "My topic");
  });
});
