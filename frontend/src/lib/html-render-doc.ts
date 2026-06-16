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

/** 捕获 iframe 内错误与渲染状态，postMessage 到父页面（sandbox 无 allow-same-origin 时父页无法读 iframe DOM） */
const DIAG_REPORTER =
  "<scr" +
  "ipt>(function(){function send(p){try{parent.postMessage(Object.assign({__apodDiag:1},p),'*')}catch(e){}}function snap(){send({phase:'snap',echarts:typeof echarts,canvas:document.querySelectorAll('canvas').length,chartEl:!!document.getElementById('chart'),bodyH:document.body?document.body.offsetHeight:0})}window.addEventListener('error',function(e){send({phase:'error',message:e.message,source:e.filename,line:e.lineno})});window.addEventListener('unhandledrejection',function(e){send({phase:'reject',message:String(e.reason)})});setTimeout(snap,500);setTimeout(snap,2000);setTimeout(snap,5000);setTimeout(function(){if(typeof echarts==='undefined')send({phase:'timeout',message:'echarts still undefined after 5s'})},5000)})();</scr" +
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

const READY_OPEN_RE =
  /^(?:document|window)\.addEventListener\s*\(\s*['"](?:DOMContentLoaded|load)['"]\s*,\s*(?:function\s*\(\s*\)\s*|\(\s*\)\s*=>\s*)\{/;

/** 按花括号深度剥掉 DOMContentLoaded / load 外层包裹（兼容嵌套 function） */
function unwrapReadyWrapper(content: string): string {
  let trimmed = content.trim();
  for (let depth = 0; depth < 3; depth++) {
    const m = trimmed.match(READY_OPEN_RE);
    if (!m) break;
    const start = m[0].length;
    let braces = 1;
    let i = start;
    while (i < trimmed.length && braces > 0) {
      if (trimmed[i] === "{") braces++;
      else if (trimmed[i] === "}") braces--;
      i++;
    }
    if (braces !== 0) break;
    const rest = trimmed.slice(i).trim();
    if (!/^\)\s*;?\s*$/.test(rest)) break;
    trimmed = trimmed.slice(start, i - 1).trim();
  }
  return trimmed;
}

/**
 * 将含 echarts 的内联脚本替换为：加载 vendor（失败回退 CDN）→ 轮询就绪 → 直接执行初始化。
 * 全部在一个 script 块内完成，避免 head/body 异步时序与 DOMContentLoaded 竞争。
 */
function bootstrapInlineEchartsScripts(html: string, origin: string): string {
  const local = `${origin}${ECHARTS_VENDOR_PATH}`;
  const cdn = ECHARTS_CDN;
  let replaced = false;
  const out = html.replace(INLINE_SCRIPT_RE, (full, attrs, content) => {
    if (!ECHARTS_USAGE_RE.test(content)) return full;
    if (/\bfunction\s+loadCdn\b/.test(content) && /\bfunction\s+run\b/.test(content)) return full;
    replaced = true;
    const inner = unwrapReadyWrapper(content);
    return (
      `<script${attrs}>!function(){` +
      `var done=false;var INIT=function(){${inner}};` +
      `function run(){if(done)return true;if(typeof echarts!=='undefined'){done=true;INIT();return true}return false}` +
      `function loadCdn(){var s=document.createElement('script');s.src='${cdn}';s.onload=function(){run()};document.head.appendChild(s)}` +
      `function boot(){var s=document.createElement('script');s.src='${local}';` +
      `s.onload=function(){if(!run())loadCdn()};s.onerror=loadCdn;document.head.appendChild(s)}` +
      `if(!run()){boot();var t=setInterval(function(){if(run())clearInterval(t)},50);setTimeout(function(){clearInterval(t)},30000)}}();</` +
      `script>`
    );
  });
  return replaced ? out : html;
}

/** 无内联 echarts 脚本时，在 head 注入加载器 */
function injectEchartsScript(html: string, origin: string): string {
  if (!ECHARTS_USAGE_RE.test(html)) return html;
  if (/\bfunction\s+boot\b/.test(html) || /\bfunction\s+loadCdn\b/.test(html)) return html;
  const local = `${origin}${ECHARTS_VENDOR_PATH}`;
  const cdn = ECHARTS_CDN;
  const tag =
    `<scr` +
    `ipt>!function(){function loadCdn(){var s=document.createElement('script');s.src='${cdn}';document.head.appendChild(s)}` +
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
  out = bootstrapInlineEchartsScripts(out, origin);
  out = injectEchartsScript(out, origin);
  const meta = `<meta http-equiv="Content-Security-Policy" content="${buildIframeCsp(origin)}">`;
  out = /<\/head>/i.test(out) ? out.replace(/<\/head>/i, meta + "</head>") : meta + out;
  out = /<\/body>/i.test(out)
    ? out.replace(/<\/body>/i, DIAG_REPORTER + HEIGHT_REPORTER + "</body>")
    : out + DIAG_REPORTER + HEIGHT_REPORTER;
  return out;
}
