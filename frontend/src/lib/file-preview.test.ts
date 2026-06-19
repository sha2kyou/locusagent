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

test("filePreviewKind detects pdf by extension and mime", () => {
  assert.equal(filePreviewKind("report.pdf"), "pdf");
  assert.equal(filePreviewKind("doc.bin", "application/pdf"), "pdf");
});

test("isFilePreviewable excludes binaries but allows markdown and pdf", () => {
  assert.equal(isFilePreviewable("guide.md"), true);
  assert.equal(isFilePreviewable("deepseek-balance-guide.md"), true);
  assert.equal(isFilePreviewable("report.pdf"), true);
  assert.equal(isFilePreviewable("archive.zip"), false);
});
