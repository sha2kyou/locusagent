import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { sha256HexText } from "./file-digest.ts";

describe("sha256HexText", () => {
  it("matches known empty string hash", async () => {
    const hex = await sha256HexText("");
    assert.equal(
      hex,
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });
});
