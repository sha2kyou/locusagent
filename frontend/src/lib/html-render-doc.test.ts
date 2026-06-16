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
  it("injects deferred echarts and defers inline init until load", () => {
    const doc = buildHtmlRenderSrcDoc(SAMPLE, ORIGIN);
    assert.match(doc, new RegExp(`<script defer src="${ORIGIN}${ECHARTS_VENDOR_PATH.replace(/\./g, "\\.")}"></script>`));
    assert.match(doc, /window\.addEventListener\('load',function\(\)\{[\s\S]*echarts\.init/);
    assert.ok(doc.includes('id="chart"'));
    assert.ok(doc.indexOf("defer src=") < doc.indexOf("echarts.init"));
  });

  it("strips legacy CDN echarts script tags", () => {
    const html = SAMPLE.replace(
      "</head>",
      '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script></head>',
    );
    const doc = buildHtmlRenderSrcDoc(html, ORIGIN);
    assert.doesNotMatch(doc, /cdn\.jsdelivr\.net/);
    assert.match(doc, new RegExp(`${ORIGIN}${ECHARTS_VENDOR_PATH.replace(/\./g, "\\.")}`));
  });
});
