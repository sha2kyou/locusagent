import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { normalizeLatexInput } from "./latex-normalize.ts";

describe("normalizeLatexInput", () => {
  it("fixes backspace-corrupted begin outside math", () => {
    const corrupted = "\x08egin{pmatrix}";
    assert.equal(normalizeLatexInput(corrupted), "\\begin{pmatrix}");
  });

  it("fixes frac inside block math", () => {
    const corrupted = "$$\x0crac{a}{b}$$";
    assert.equal(normalizeLatexInput(corrupted), "$$\\frac{a}{b}$$");
  });

  it("leaves CRLF inside block math unchanged", () => {
    const content = "$$\\begin{pmatrix}\r\na & b\r\n\\end{pmatrix}$$";
    assert.equal(normalizeLatexInput(content), content);
  });

  it("leaves tab-indented code fences unchanged", () => {
    const content = "```python\n\tdef foo():\n\t    pass\n```";
    assert.equal(normalizeLatexInput(content), content);
  });
});
