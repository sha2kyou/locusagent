import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import {
  Brain,
  Check,
  Code2,
  Copy,
  ExternalLink,
  Expand,
  Loader2,
  WrapText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { openExternalUrl } from "@/lib/open-external";
import { normalizeLatexInput } from "@/lib/latex-normalize";
import { CollapsibleMetaBlock } from "./CollapsibleMetaBlock";

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
        if (s.kind === "thinking")
          return (
            <ThinkingBlock
              key={`t-${i}`}
              blockId={`md-think-${hashString(s.content)}`}
              content={s.content}
            />
          );
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
          <a
            href={href}
            rel="noreferrer"
            className="text-brand underline underline-offset-2"
          >
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
  const { t } = useTranslation();
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
    <div ref={ref} className="apod-code-block group my-3 overflow-hidden rounded-xl">
      <div className="apod-code-block-header flex items-center justify-between px-3.5 py-2">
        <span className="apod-code-block-lang rounded-md px-1.5 py-0.5 font-mono text-[11px] lowercase tracking-wide">
          {lang || "code"}
        </span>
        <div className="apod-code-block-actions flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => setWrap((v) => !v)}
            className={cn(
              "apod-code-block-action inline-flex size-6 items-center justify-center rounded-md",
              wrap && "apod-code-block-action-active",
            )}
            aria-label={wrap ? t("chat.markdown.wrapOff") : t("chat.markdown.wrapOn")}
            title={wrap ? t("chat.markdown.wrapOff") : t("chat.markdown.wrapOn")}
          >
            <WrapText className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={copy}
            className="apod-code-block-action inline-flex size-6 items-center justify-center rounded-md"
            aria-label={t("chat.markdown.copyCode")}
            title={t("chat.markdown.copy")}
          >
            {copied ? (
              <Check className="size-3.5 apod-code-block-action-success" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </button>
        </div>
      </div>
      <pre
        className={cn(
          "apod-code-block-body overflow-x-auto p-4 text-[13px] leading-relaxed",
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
  label = "thinking",
  blockId,
}: {
  content: string;
  isActive?: boolean;
  label?: string;
  blockId?: string;
}) {
  return (
    <CollapsibleMetaBlock
      blockId={blockId ?? `think-${hashString(content)}`}
      active={isActive}
      title={label}
      activeTitle="thinking"
      running={isActive}
      icon={<Brain className="size-3.5" />}
      preview={content}
    >
      <div className="apod-prose text-[13px] text-muted-foreground/90">
        <MarkdownBlock text={content} />
      </div>
    </CollapsibleMetaBlock>
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
  const { t } = useTranslation();
  return (
    <div className="my-3 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center gap-2 border-b border-border bg-surface-2/60 px-3 py-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> {t("chat.markdown.vizGenerating")}
      </div>
      <div className="space-y-2 p-4">
        <div className="h-3 w-1/3 animate-pulse rounded bg-muted-foreground/15" />
        <div className="h-40 w-full animate-pulse rounded bg-muted-foreground/10" />
      </div>
    </div>
  );
}

export function HtmlRender({ html }: { html: string }) {
  const { t } = useTranslation();
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
    const dataUrl = `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
    void openExternalUrl(dataUrl);
  };
  const fullscreen = () => void ref.current?.requestFullscreen?.();

  if (!html.trim()) {
    return (
      <div className="my-3 rounded-lg border border-border bg-surface/40 px-3 py-4 text-center text-xs text-muted-foreground">
        {t("chat.markdown.vizEmpty")}
      </div>
    );
  }

  const tools: Array<{ key: string; icon: ReactNode; label: string; onClick: () => void }> = [
    { key: "full", icon: <Expand className="size-3.5" />, label: t("chat.markdown.fullscreen"), onClick: fullscreen },
    { key: "open", icon: <ExternalLink className="size-3.5" />, label: t("chat.markdown.openInNewWindow"), onClick: openNew },
    { key: "copy", icon: copied ? <Check className="size-3.5 text-success" /> : <Code2 className="size-3.5" />, label: t("chat.markdown.copySource"), onClick: copy },
  ];

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border bg-surface-2/60 px-3 py-1.5 text-xs text-muted-foreground">
        <span>{t("chat.markdown.htmlPreview")}</span>
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
