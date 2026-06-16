import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildHtmlRenderSrcDoc, ECHARTS_VENDOR_PATH } from "./html-render-doc.ts";

const ORIGIN = "http://127.0.0.1:21223";

const SAMPLE = `<!doctype html>
<html>
<head><meta charset="UTF-8"><title>demo</title></head>
<body>
  <div id="chart" style="width:100%;height:320px"></div>
  <script>
    var chart = echarts.init(document.getElementById('chart'));
    chart.setOption({ series: [{ type: 'bar', data: [1, 2, 3] }] });
  </script>
</body>
</html>`;

describe("buildHtmlRenderSrcDoc", () => {
  it("injects local vendor loader with CDN fallback and polling init", () => {
    const doc = buildHtmlRenderSrcDoc(SAMPLE, ORIGIN);
    // local vendor is referenced in the loader
    assert.match(doc, new RegExp(`s\\.src='${ORIGIN}${ECHARTS_VENDOR_PATH.replace(/\./g, "\\.")}'`));
    // CDN fallback is present
    assert.match(doc, /cdn\.jsdelivr\.net\/npm\/echarts/);
    // init code is wrapped in polling (go() + setInterval pattern)
    assert.match(doc, /function go\(\)[\s\S]*echarts\.init[\s\S]*setInterval/);
    assert.ok(doc.includes('id="chart"'));
  });

  it("unwraps DOMContentLoaded and waits for async echarts", () => {
    const html = SAMPLE.replace(
      "<script>",
      `<script>
document.addEventListener('DOMContentLoaded', function() {`,
    ).replace(
      "</script>",
      `});
</script>`,
    );
    const doc = buildHtmlRenderSrcDoc(html, ORIGIN);
    assert.doesNotMatch(doc, /DOMContentLoaded/);
    assert.match(doc, /function go\(\)[\s\S]*echarts\.init[\s\S]*setInterval/);
  });

  it("strips legacy CDN echarts script tags and replaces with local loader", () => {
    const html = SAMPLE.replace(
      "</head>",
      '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script></head>',
    );
    const doc = buildHtmlRenderSrcDoc(html, ORIGIN);
    // stripped CDN tag should not appear as a <script src> tag anymore
    assert.doesNotMatch(doc, /<script[^>]*src=["'][^"']*cdn\.jsdelivr\.net[^"']*["'][^>]*>/);
    // local vendor is referenced
    assert.match(doc, new RegExp(`${ORIGIN}${ECHARTS_VENDOR_PATH.replace(/\./g, "\\.")}`));
  });
});
