/** 与 frontend/public/vendor/echarts-5.5.1.min.js 及 html-render skill 保持一致 */
export const ECHARTS_VERSION = "5.5.1";
export const ECHARTS_VENDOR_PATH = `/vendor/echarts-${ECHARTS_VERSION}.min.js`;

const ECHARTS_SCRIPT_RE =
  /<script[^>]*\bsrc=["'][^"']*echarts[^"']*["'][^>]*>\s*<\/script>/gi;
const ECHARTS_USAGE_RE = /\becharts\b/i;
const INLINE_SCRIPT_RE = /<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/gi;

const HEIGHT_REPORTER =
  "<scr" +
  "ipt>(function(){function r(){try{var h=Math.max(document.documentElement.scrollHeight,document.body?document.body.scrollHeight:0);parent.postMessage({__apodHeight:h},'*')}catch(e){}}window.addEventListener('load',r);window.addEventListener('resize',r);if(window.ResizeObserver){try{new ResizeObserver(r).observe(document.documentElement)}catch(e){}}setTimeout(r,200);setTimeout(r,800)})();</scr" +
  "ipt>";

function buildIframeCsp(origin: string): string {
  return (
    "default-src 'none'; " +
    `script-src 'unsafe-inline' 'unsafe-eval' ${origin} http: https:; ` +
    `style-src 'unsafe-inline' ${origin} http: https:; ` +
    "img-src data: blob: http: https:; " +
    "font-src data: http: https:; " +
    "connect-src http: https:; " +
    "base-uri 'none'; form-action 'none'"
  );
}

function stripEchartsScripts(html: string): string {
  return html.replace(ECHARTS_SCRIPT_RE, "");
}

const ECHARTS_CDN = `https://cdn.jsdelivr.net/npm/echarts@${ECHARTS_VERSION}/dist/echarts.min.js`;

/** 剥掉 Agent 常见的 DOMContentLoaded / load 包裹，避免与异步注入的 ECharts 发生时序竞争 */
function unwrapReadyWrapper(content: string): string {
  const trimmed = content.trim();
  const m = trimmed.match(
    /^(?:document|window)\.addEventListener\s*\(\s*['"](?:DOMContentLoaded|load)['"]\s*,\s*function\s*\(\s*\)\s*\{([\s\S]*)\}\s*\)\s*;?\s*$/,
  );
  return m ? m[1].trim() : trimmed;
}

/**
 * 将内联 echarts 初始化改为轮询等待 echarts 可用后执行。
 * ECharts 由 injectEchartsScript 异步注入，不能再依赖 DOMContentLoaded / load。
 */
function deferInlineEchartsScripts(html: string): string {
  return html.replace(INLINE_SCRIPT_RE, (full, attrs, content) => {
    if (!ECHARTS_USAGE_RE.test(content)) return full;
    const inner = unwrapReadyWrapper(content);
    return (
      `<script${attrs}>!function(){` +
      `function go(){${inner}}` +
      `if(typeof echarts!=='undefined'){go()}` +
      `else{var t=setInterval(function(){if(typeof echarts!=='undefined'){clearInterval(t);go()}},50);` +
      `setTimeout(function(){clearInterval(t)},30000)}` +
      `}();</` +
      `script>`
    );
  });
}

/**
 * 注入 ECharts 加载器：优先本地 vendor，onload 后检测 echarts 是否可用；
 * 若本地返回非 JS 内容（如 index.html SPA fallback）或加载失败，则回退到 CDN。
 */
function injectEchartsScript(html: string, origin: string): string {
  if (!ECHARTS_USAGE_RE.test(html)) return html;
  const local = `${origin}${ECHARTS_VENDOR_PATH}`;
  const cdn = ECHARTS_CDN;
  const tag =
    `<scr` +
    `ipt>!function(){` +
    `function loadCdn(){var s=document.createElement('script');s.src='${cdn}';document.head.appendChild(s)}` +
    `var s=document.createElement('script');s.src='${local}';` +
    `s.onload=function(){if(typeof echarts==='undefined')loadCdn()};` +
    `s.onerror=loadCdn;` +
    `document.head.appendChild(s)}();</` +
    `script>`;
  if (/<\/head>/i.test(html)) return html.replace(/<\/head>/i, `${tag}</head>`);
  return tag + html;
}

/** 为 [HTML_RENDER] iframe 生成 srcdoc：注入本地 ECharts、CSP 与高度上报脚本 */
export function buildHtmlRenderSrcDoc(html: string, origin: string): string {
  let out = stripEchartsScripts(html);
  out = deferInlineEchartsScripts(out);
  out = injectEchartsScript(out, origin);
  const meta = `<meta http-equiv="Content-Security-Policy" content="${buildIframeCsp(origin)}">`;
  out = /<\/head>/i.test(out) ? out.replace(/<\/head>/i, meta + "</head>") : meta + out;
  out = /<\/body>/i.test(out)
    ? out.replace(/<\/body>/i, HEIGHT_REPORTER + "</body>")
    : out + HEIGHT_REPORTER;
  return out;
}
