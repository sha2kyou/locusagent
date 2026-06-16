import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
  it("bootstraps inline echarts with vendor + CDN in one script", () => {
    const doc = buildHtmlRenderSrcDoc(SAMPLE, ORIGIN);
    assert.match(doc, new RegExp(`s\\.src='${ORIGIN}${ECHARTS_VENDOR_PATH.replace(/\./g, "\\.")}'`));
    assert.match(doc, /cdn\.jsdelivr\.net\/npm\/echarts/);
    assert.match(doc, /var INIT=function\(\)[\s\S]*echarts\.init/);
    assert.doesNotMatch(doc, /DOMContentLoaded/);
    assert.ok(doc.includes('id="chart"'));
  });

  it("unwraps DOMContentLoaded with nested handlers (real agent output)", () => {
    const html = SAMPLE.replace(
      "<script>",
      `<script>
document.addEventListener('DOMContentLoaded', function() {`,
    ).replace(
      "chart.setOption({ series: [{ type: 'bar', data: [1, 2, 3] }] });",
      `chart.setOption({ series: [{ type: 'bar', data: [1, 2, 3] }] });
  window.addEventListener('resize', function() { chart.resize(); });`,
    ).replace(
      "</script>",
      `});
</script>`,
    );
    const doc = buildHtmlRenderSrcDoc(html, ORIGIN);
    assert.doesNotMatch(doc, /DOMContentLoaded/);
    assert.match(doc, /var INIT=function\(\)[\s\S]*echarts\.init[\s\S]*resize/);
  });

  it("handles saved session html (msg804)", () => {
    let raw = "";
    try {
      raw = readFileSync("/tmp/msg804.txt", "utf8");
    } catch {
      return;
    }
    const html = raw.replace(/^\[HTML_RENDER\]\n?/, "").replace(/\n?\[\/HTML_RENDER\]$/, "");
    const doc = buildHtmlRenderSrcDoc(html, ORIGIN);
    assert.doesNotMatch(doc, /DOMContentLoaded/);
    assert.match(doc, /var INIT=function\(\)/);
    assert.match(doc, /__apodDiag/);
  });

  it("strips legacy CDN echarts script tags and replaces with bootstrap", () => {
    const html = SAMPLE.replace(
      "</head>",
      '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script></head>',
    );
    const doc = buildHtmlRenderSrcDoc(html, ORIGIN);
    assert.doesNotMatch(doc, /<script[^>]*src=["'][^"']*cdn\.jsdelivr\.net[^"']*["'][^>]*>/);
    assert.match(doc, new RegExp(`${ORIGIN}${ECHARTS_VENDOR_PATH.replace(/\./g, "\\.")}`));
  });
});
