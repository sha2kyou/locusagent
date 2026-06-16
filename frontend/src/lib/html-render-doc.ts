/** 与 frontend/public/vendor/echarts-5.5.1.min.js 及 html-render skill 保持一致 */
export const ECHARTS_VERSION = "5.5.1";
export const ECHARTS_VENDOR_PATH = `/vendor/echarts-${ECHARTS_VERSION}.min.js`;

const ECHARTS_SCRIPT_RE =
  /<script[^>]*\bsrc=["'][^"']*echarts[^"']*["'][^>]*>\s*<\/script>/gi;
const ECHARTS_USAGE_RE = /\becharts\b/i;

const HEIGHT_REPORTER =
  "<scr" +
  "ipt>(function(){function r(){try{var h=Math.max(document.documentElement.scrollHeight,document.body?document.body.scrollHeight:0);parent.postMessage({__apodHeight:h},'*')}catch(e){}}window.addEventListener('load',r);window.addEventListener('resize',r);if(window.ResizeObserver){try{new ResizeObserver(r).observe(document.documentElement)}catch(e){}}setTimeout(r,200);setTimeout(r,800)})();</scr" +
  "ipt>";

function buildIframeCsp(origin: string): string {
  return (
    "default-src 'none'; " +
    `script-src 'unsafe-inline' 'unsafe-eval' ${origin}; ` +
    `style-src 'unsafe-inline' ${origin}; ` +
    "img-src data: blob: https:; " +
    "font-src data: https:; " +
    "connect-src https:; " +
    "base-uri 'none'; form-action 'none'"
  );
}

function stripEchartsScripts(html: string): string {
  return html.replace(ECHARTS_SCRIPT_RE, "");
}

function injectEchartsScript(html: string, origin: string): string {
  if (!ECHARTS_USAGE_RE.test(html)) return html;
  const tag = `<script src="${origin}${ECHARTS_VENDOR_PATH}"></script>`;
  if (/<\/head>/i.test(html)) return html.replace(/<\/head>/i, `${tag}</head>`);
  return tag + html;
}

/** 为 [HTML_RENDER] iframe 生成 srcdoc：注入本地 ECharts、CSP 与高度上报脚本 */
export function buildHtmlRenderSrcDoc(html: string, origin: string): string {
  let out = stripEchartsScripts(html);
  out = injectEchartsScript(out, origin);
  const meta = `<meta http-equiv="Content-Security-Policy" content="${buildIframeCsp(origin)}">`;
  out = /<\/head>/i.test(out) ? out.replace(/<\/head>/i, meta + "</head>") : meta + out;
  out = /<\/body>/i.test(out)
    ? out.replace(/<\/body>/i, HEIGHT_REPORTER + "</body>")
    : out + HEIGHT_REPORTER;
  return out;
}
