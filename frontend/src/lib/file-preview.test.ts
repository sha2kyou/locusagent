import { test } from "node:test";
import assert from "node:assert/strict";
import { filePreviewKind, highlightLanguage, isFilePreviewable } from "./file-preview.ts";

test("filePreviewKind detects markdown and code", () => {
  assert.equal(filePreviewKind("SKILL.md"), "markdown");
  assert.equal(filePreviewKind("scripts/run.sh"), "code");
  assert.equal(filePreviewKind("app.ts"), "code");
});

test("filePreviewKind detects images by extension and mime", () => {
  assert.equal(filePreviewKind("assets/logo.png"), "image");
  assert.equal(filePreviewKind("photo.bin", "image/jpeg"), "image");
});

test("isFilePreviewable excludes binaries but allows markdown", () => {
  assert.equal(isFilePreviewable("guide.md"), true);
  assert.equal(isFilePreviewable("deepseek-balance-guide.md"), true);
  assert.equal(isFilePreviewable("report.pdf"), false);
  assert.equal(isFilePreviewable("archive.zip"), false);
});
