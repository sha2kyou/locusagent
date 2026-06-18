import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";

import { normalizeBareAutolinks } from "./markdown-autolink.ts";

function autolinkUrls(text: string): string[] {
  const tree = unified().use(remarkParse).use(remarkGfm).parse(normalizeBareAutolinks(text));
  const urls: string[] = [];
  visit(tree, "link", (node) => {
    if ("url" in node && typeof node.url === "string") urls.push(node.url);
  });
  return urls;
}

describe("normalizeBareAutolinks", () => {
  it("stops autolink before CJK punctuation glued to URL", () => {
    const text = "https://github.com/kageroumado/phosphene/commits/main/。同时，也可以搜索";
    assert.deepEqual(autolinkUrls(text), ["https://github.com/kageroumado/phosphene/commits/main/"]);
  });

  it("leaves URL followed by ASCII space unchanged", () => {
    const text = "see https://example.com/foo bar";
    assert.deepEqual(autolinkUrls(text), ["https://example.com/foo"]);
  });

  it("does not modify URLs inside fenced code", () => {
    const text = "```\nhttps://example.com/。test\n```";
    assert.equal(normalizeBareAutolinks(text), text);
  });

  it("does not double-wrap angle-bracket URLs", () => {
    const text = "<https://example.com/>。note";
    assert.deepEqual(autolinkUrls(text), ["https://example.com/"]);
  });
});
