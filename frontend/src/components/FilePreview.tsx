import { useTranslation } from "react-i18next";
import { ProseMarkdown } from "@/features/chat/Markdown";
import {
  buildDataUrl,
  filePreviewKind,
  highlightLanguage,
  type FilePreviewKind,
} from "@/lib/file-preview";
import { cn } from "@/lib/utils";

export interface FilePreviewProps {
  filename: string;
  content?: string | null;
  contentBase64?: string | null;
  mimeType?: string | null;
  /** 显式图片地址（附件 data URL 等），优先于 contentBase64 */
  imageSrc?: string | null;
  /** PDF 等文档 blob URL（由 fetchAttachmentPreview 生成） */
  documentSrc?: string | null;
  emptyText?: string;
  unsupportedText?: string;
  truncated?: boolean;
  truncatedText?: string;
  className?: string;
}

function resolveImageSrc(props: FilePreviewProps): string | null {
  if (props.imageSrc) return props.imageSrc;
  if (props.contentBase64 && props.mimeType) {
    return buildDataUrl(props.mimeType, props.contentBase64);
  }
  return null;
}

function PlainTextBlock({ content, className }: { content: string; className?: string }) {
  return (
    <pre
      className={cn(
        "whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-mono text-xs text-foreground",
        className,
      )}
    >
      {content}
    </pre>
  );
}

function CodePreview({ filename, content }: { filename: string; content: string }) {
  const lang = highlightLanguage(filename);
  return <ProseMarkdown text={`\`\`\`${lang}\n${content}\n\`\`\``} enableMath={false} />;
}

function ImagePreview({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="rounded-md bg-surface-2 p-2">
      <img src={src} alt={alt} className="mx-auto w-auto max-w-full rounded object-contain" />
    </div>
  );
}

function PdfPreview({ src, title }: { src: string; title: string }) {
  const { t } = useTranslation();
  return (
    <object
      data={src}
      type="application/pdf"
      title={title}
      className="block h-[min(70vh,720px)] w-full rounded-md border border-border bg-surface-2"
    >
      <embed src={src} type="application/pdf" className="h-[min(70vh,720px)] w-full" title={title} />
      <p className="p-3 text-sm text-muted-foreground">
        {t("chat.attachment.pdfPreviewUnavailable")}{" "}
        <a href={src} target="_blank" rel="noreferrer" className="underline">
          {t("chat.attachment.openPdf")}
        </a>
      </p>
    </object>
  );
}

function renderByKind(
  kind: FilePreviewKind,
  props: FilePreviewProps,
  content: string,
  imageSrc: string | null,
  documentSrc: string | null,
) {
  switch (kind) {
    case "markdown":
      return <ProseMarkdown text={content} />;
    case "code":
      return <CodePreview filename={props.filename} content={content} />;
    case "image":
      return imageSrc ? (
        <ImagePreview src={imageSrc} alt={props.filename} />
      ) : (
        <p className="text-sm text-muted-foreground">{props.unsupportedText ?? "Preview not available."}</p>
      );
    case "pdf":
      return documentSrc ? (
        <PdfPreview src={documentSrc} title={props.filename} />
      ) : (
        <p className="text-sm text-muted-foreground">{props.unsupportedText ?? "Preview not available."}</p>
      );
    case "text":
      return <PlainTextBlock content={content} />;
    default:
      return (
        <p className="text-sm text-muted-foreground">{props.unsupportedText ?? "Preview not supported for this file type."}</p>
      );
  }
}

export function FilePreview({
  filename,
  content,
  contentBase64,
  mimeType,
  imageSrc: imageSrcProp,
  documentSrc,
  emptyText = "Empty file.",
  unsupportedText,
  truncated,
  truncatedText,
  className,
}: FilePreviewProps) {
  const kind = filePreviewKind(filename, mimeType);
  const imageSrc = resolveImageSrc({
    filename,
    content,
    contentBase64,
    mimeType,
    imageSrc: imageSrcProp,
  });
  const text = content ?? "";

  return (
    <div className={cn("space-y-3", className)}>
      {kind === "image" ? (
        imageSrc ? (
          <ImagePreview src={imageSrc} alt={filename} />
        ) : (
          <p className="text-sm text-muted-foreground">{unsupportedText ?? emptyText}</p>
        )
      ) : kind === "pdf" ? (
        documentSrc ? (
          <PdfPreview src={documentSrc} title={filename} />
        ) : (
          <p className="text-sm text-muted-foreground">{unsupportedText ?? emptyText}</p>
        )
      ) : !text.trim() ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        renderByKind(
          kind,
          { filename, content, contentBase64, mimeType, imageSrc: imageSrcProp, documentSrc, emptyText, unsupportedText },
          text,
          imageSrc,
          documentSrc ?? null,
        )
      )}
      {truncated && truncatedText ? <p className="text-xs text-warning">{truncatedText}</p> : null}
    </div>
  );
}
