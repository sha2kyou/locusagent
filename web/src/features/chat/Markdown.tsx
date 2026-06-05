import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import {
  Check,
  ChevronRight,
  Code2,
  Copy,
  ExternalLink,
  Expand,
  Loader2,
  WrapText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { normalizeLatexInput } from "@/lib/latex-normalize";

interface Segment {
  kind: "md" | "thinking" | "html" | "html-pending";
  content: string;
}

const HTML_OPEN = "[HTML_RENDER]";

const THINKING_RE = /<think(?:ing)?>([\s\S]*?)<\/think(?:ing)?>/gi;
const HTML_RE = /\[HTML_RENDER\]([\s\S]*?)\[\/HTML_RENDER\]/gi;

/** 切出 thinking 折叠块 */
function splitThinking(input: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  THINKING_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = THINKING_RE.exec(input)) !== null) {
    if (m.index > last) out.push({ kind: "md", content: input.slice(last, m.index) });
    out.push({ kind: "thinking", content: m[1] });
    last = m.index + m[0].length;
  }
  if (last < input.length) out.push({ kind: "md", content: input.slice(last) });
  return out;
}

/** 切出已闭合的 HTML 块，并对流式中未闭合的开标记产出占位 */
function splitHtml(input: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  HTML_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = HTML_RE.exec(input)) !== null) {
    if (m.index > last) out.push({ kind: "md", content: input.slice(last, m.index) });
    out.push({ kind: "html", content: m[1] });
    last = m.index + m[0].length;
  }
  const tail = input.slice(last);
  const openIdx = tail.indexOf(HTML_OPEN);
  if (openIdx >= 0) {
    // 仅有开标记、尚无闭标记：流式生成中 → 占位
    if (openIdx > 0) out.push({ kind: "md", content: tail.slice(0, openIdx) });
    out.push({ kind: "html-pending", content: "" });
  } else if (tail.length) {
    out.push({ kind: "md", content: tail });
  }
  return out;
}

/** 把文本切成普通 markdown / thinking 折叠块 / HTML 渲染块 */
function segment(text: string): Segment[] {
  const segs: Segment[] = [];
  for (const s of splitThinking(text)) {
    if (s.kind === "md") segs.push(...splitHtml(s.content));
    else segs.push(s);
  }
  return segs.filter((s) => s.content.trim().length > 0 || s.kind !== "md");
}

/** 轻量字符串 hash，用作渲染 key，避免段顺序变化导致 iframe 重载 */
function hashString(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export const Markdown = memo(function Markdown({ text, enableMath = true }: { text: string; enableMath?: boolean }) {
  const segs = segment(text);
  return (
    <div className="apod-prose">
      {segs.map((s, i) => {
        if (s.kind === "thinking") return <ThinkingBlock key={`t-${i}`} content={s.content} />;
        if (s.kind === "html") return <HtmlRender key={`h-${hashString(s.content)}`} html={s.content} />;
        if (s.kind === "html-pending") return <HtmlPending key="h-pending" />;
        return <MarkdownBlock key={`m-${i}`} text={s.content} enableMath={enableMath} />;
      })}
    </div>
  );
});

function MarkdownBlock({ text, enableMath = true }: { text: string; enableMath?: boolean }) {
  const normalized = useMemo(
    () => (enableMath ? normalizeLatexInput(text) : text),
    [text, enableMath],
  );
  const remarkPlugins = enableMath ? [remarkMath, remarkGfm] : [remarkGfm];
  const rehypePlugins = enableMath ? [rehypeKatex, rehypeHighlight] : [rehypeHighlight];
  return (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={{
        pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
        table: ({ children, ...props }) => (
          <div className="apod-table-scroll">
            <table {...props}>{children}</table>
          </div>
        ),
        a: ({ children, href }) => (
          <a href={href} target="_blank" rel="noreferrer" className="text-brand underline underline-offset-2">
            {children}
          </a>
        ),
      }}
    >
      {normalized}
    </ReactMarkdown>
  );
}

/** 无 thinking/HTML 分段，用于用户气泡等纯 Markdown+公式场景 */
export function ProseMarkdown({
  text,
  className,
  enableMath = true,
}: {
  text: string;
  className?: string;
  enableMath?: boolean;
}) {
  return (
    <div className={cn("apod-prose max-w-none", className)}>
      <MarkdownBlock text={text} enableMath={enableMath} />
    </div>
  );
}

function extractLang(children: ReactNode): string {
  const child = Array.isArray(children) ? children[0] : children;
  const cls = (child as { props?: { className?: string } } | null)?.props?.className;
  const m = cls?.match(/language-([\w-]+)/);
  return m?.[1] ?? "";
}

function CodeBlock({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const [wrap, setWrap] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const lang = extractLang(children);

  const copy = () => {
    const txt = ref.current?.querySelector("code")?.textContent ?? "";
    void navigator.clipboard.writeText(txt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div ref={ref} className="group my-3 overflow-hidden rounded-xl border border-border shadow-xs">
      <div className="flex items-center justify-between border-b border-border bg-surface-2/80 px-3.5 py-2">
        <span className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-[11px] lowercase tracking-wide text-muted-foreground">
          {lang || "code"}
        </span>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => setWrap((v) => !v)}
            className={cn(
              "inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-surface hover:text-foreground",
              wrap && "bg-surface text-foreground",
            )}
            aria-label="自动换行"
            title={wrap ? "取消换行" : "自动换行"}
          >
            <WrapText className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={copy}
            className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-surface hover:text-foreground"
            aria-label="复制代码"
            title="复制"
          >
            {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
          </button>
        </div>
      </div>
      <pre
        className={cn(
          "overflow-x-auto bg-surface-2/50 p-4 text-[13px] leading-relaxed",
          wrap && "whitespace-pre-wrap wrap-break-word",
        )}
      >
        {children}
      </pre>
    </div>
  );
}

export function ThinkingBlock({
  content,
  isActive = false,
  defaultOpen = false,
  label = "思考过程",
}: {
  content: string;
  isActive?: boolean;
  defaultOpen?: boolean;
  label?: string;
}) {
  const [open, setOpen] = useState(defaultOpen || isActive);
  const displayLabel = isActive ? "思考中" : label;

  useEffect(() => {
    if (isActive) setOpen(true);
  }, [isActive]);

  return (
    <div className="my-2 overflow-hidden rounded-xl border border-border/70 bg-surface/30 shadow-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-surface/60"
      >
        {isActive ? (
          <span className="flex size-3.5 shrink-0 items-center justify-center">
            <span className="size-2 animate-pulse rounded-full bg-muted-foreground/60" />
          </span>
        ) : (
          <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground/70 transition-transform duration-150", open && "rotate-90")} />
        )}
        <span className="shrink-0 whitespace-nowrap text-[12px] font-medium text-muted-foreground">
          {displayLabel}
        </span>
        {!open && content ? (
          <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground/50">
            {content.slice(0, 80).replace(/\n/g, " ")}
          </span>
        ) : null}
      </button>
      {open && (
        <div className="apod-prose border-t border-border/60 px-3.5 py-3 text-[13px] text-muted-foreground/90">
          <MarkdownBlock text={content} />
        </div>
      )}
    </div>
  );
}

// 沙箱内容安全策略：阻断非 https 资源与跨源 same-origin 访问，inline 用于内联 echarts 初始化
const IFRAME_CSP =
  "default-src 'none'; " +
  "script-src 'unsafe-inline' 'unsafe-eval' https:; " +
  "style-src 'unsafe-inline' https:; " +
  "img-src data: blob: https:; " +
  "font-src data: https:; " +
  "connect-src https:; " +
  "base-uri 'none'; form-action 'none'";

// 高度上报脚本：sandbox 无 allow-same-origin，父窗口通过 postMessage 读取内容高度
const HEIGHT_REPORTER =
  "<scr" +
  "ipt>(function(){function r(){try{var h=Math.max(document.documentElement.scrollHeight,document.body?document.body.scrollHeight:0);parent.postMessage({__apodHeight:h},'*')}catch(e){}}window.addEventListener('load',r);window.addEventListener('resize',r);if(window.ResizeObserver){try{new ResizeObserver(r).observe(document.documentElement)}catch(e){}}setTimeout(r,200);setTimeout(r,800)})();</scr" +
  "ipt>";

function buildSrcDoc(html: string): string {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${IFRAME_CSP}">`;
  let out = html;
  out = /<\/head>/i.test(out) ? out.replace(/<\/head>/i, meta + "</head>") : meta + out;
  out = /<\/body>/i.test(out) ? out.replace(/<\/body>/i, HEIGHT_REPORTER + "</body>") : out + HEIGHT_REPORTER;
  return out;
}

function HtmlPending() {
  return (
    <div className="my-3 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center gap-2 border-b border-border bg-surface-2/60 px-3 py-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> 正在生成可视化…
      </div>
      <div className="space-y-2 p-4">
        <div className="h-3 w-1/3 animate-pulse rounded bg-muted-foreground/15" />
        <div className="h-40 w-full animate-pulse rounded bg-muted-foreground/10" />
      </div>
    </div>
  );
}

export function HtmlRender({ html }: { html: string }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [copied, setCopied] = useState(false);
  const [height, setHeight] = useState(320);

  const doc = useMemo(() => buildSrcDoc(html), [html]);

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.source !== ref.current?.contentWindow) return;
      const h = (e.data as { __apodHeight?: number } | null)?.__apodHeight;
      if (typeof h === "number" && h > 0) {
        const max = Math.round(window.innerHeight * 0.8);
        setHeight(Math.min(Math.max(Math.ceil(h), 160), max));
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  const copy = () => {
    void navigator.clipboard.writeText(html);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const openNew = () => {
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const win = window.open(url, "_blank", "noopener");
    if (win) win.addEventListener?.("load", () => URL.revokeObjectURL(url));
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  };
  const fullscreen = () => void ref.current?.requestFullscreen?.();

  if (!html.trim()) {
    return (
      <div className="my-3 rounded-lg border border-border bg-surface/40 px-3 py-4 text-center text-xs text-muted-foreground">
        无可渲染内容
      </div>
    );
  }

  const tools: Array<{ key: string; icon: ReactNode; label: string; onClick: () => void }> = [
    { key: "full", icon: <Expand className="size-3.5" />, label: "全屏", onClick: fullscreen },
    { key: "open", icon: <ExternalLink className="size-3.5" />, label: "新窗口打开", onClick: openNew },
    { key: "copy", icon: copied ? <Check className="size-3.5 text-success" /> : <Code2 className="size-3.5" />, label: "复制源码", onClick: copy },
  ];

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border bg-surface-2/60 px-3 py-1.5 text-xs text-muted-foreground">
        <span>HTML 预览</span>
        <div className="flex items-center gap-0.5">
          {tools.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={t.onClick}
              className="inline-flex size-6 items-center justify-center rounded transition hover:text-foreground"
              aria-label={t.label}
              title={t.label}
            >
              {t.icon}
            </button>
          ))}
        </div>
      </div>
      <iframe
        ref={ref}
        title="html-render"
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        allowFullScreen
        style={{ height }}
        className="w-full bg-white transition-[height] duration-150"
        srcDoc={doc}
      />
    </div>
  );
}
