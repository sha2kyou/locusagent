import { memo, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { Brain, Check, Copy, WrapText } from "lucide-react";
import { cn } from "@/lib/utils";
import { normalizeBareAutolinks } from "@/lib/markdown-autolink";
import { normalizeLatexInput } from "@/lib/latex-normalize";
import { CollapsibleMetaBlock } from "./CollapsibleMetaBlock";

interface Segment {
  kind: "md" | "thinking";
  content: string;
}

const THINKING_RE = /<think(?:ing)?>([\s\S]*?)<\/think(?:ing)?>/gi;

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

/** 轻量字符串 hash，用作渲染 key */
function hashString(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export const Markdown = memo(function Markdown({ text, enableMath = true }: { text: string; enableMath?: boolean }) {
  const segs = splitThinking(text).filter((s) => s.content.trim().length > 0 || s.kind !== "md");
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
        return <MarkdownBlock key={`m-${i}`} text={s.content} enableMath={enableMath} />;
      })}
    </div>
  );
});

function MarkdownBlock({ text, enableMath = true }: { text: string; enableMath?: boolean }) {
  const normalized = useMemo(() => {
    const withAutolinks = normalizeBareAutolinks(text);
    return enableMath ? normalizeLatexInput(withAutolinks) : withAutolinks;
  }, [text, enableMath]);
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

/** 无 thinking 分段，用于用户气泡等纯 Markdown+公式场景 */
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
