import { test } from "node:test";
import assert from "node:assert/strict";
import { filePreviewKind, highlightLanguage } from "./file-preview.ts";

test("filePreviewKind detects markdown and code", () => {
  assert.equal(filePreviewKind("SKILL.md"), "markdown");
  assert.equal(filePreviewKind("scripts/run.sh"), "code");
  assert.equal(filePreviewKind("app.ts"), "code");
});

test("filePreviewKind detects images by extension and mime", () => {
  assert.equal(filePreviewKind("assets/logo.png"), "image");
  assert.equal(filePreviewKind("photo.bin", "image/jpeg"), "image");
});

test("highlightLanguage maps common extensions", () => {
  assert.equal(highlightLanguage("run.sh"), "bash");
  assert.equal(highlightLanguage("index.tsx"), "tsx");
});
