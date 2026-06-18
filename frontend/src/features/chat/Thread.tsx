import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAui,
  useMessage,
  useThreadRuntime,
  type TextMessagePartComponent,
} from "@assistant-ui/react";
import { ArrowDown, ArrowUp, Check, Copy, Download, Paperclip, RotateCcw, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useImeEnterGuard } from "@/lib/ime-enter";
import { useCopy } from "@/lib/useCopy";
import {
  getAgentComposerPlaceholder,
} from "@/lib/agent-status-copy";
import { Markdown, ThinkingBlock } from "./Markdown";
import { FilePreview } from "@/components/FilePreview";
import type { ChatMessage } from "./model";
import { ToolPartView } from "./ToolEvent";
import { extractLatestTodoPlan, applyHistoricalTodoInterrupt, isTodoTool, type TodoPlan } from "./todo";
import { TodoProgressPanel } from "./TodoProgressPanel";
import { useChat } from "./ChatProvider";
import type { ChatAttachment } from "./model";
import { downloadAttachment, attachmentDownloadUrl, fetchAttachmentPreview } from "@/api/endpoints";
import { isFilePreviewable } from "@/lib/file-preview";
import { Drawer } from "@/components/ui/drawer";
import { useTimeFormatters } from "@/lib/use-app-timezone";
import { isDesktopApp } from "@/lib/desktop-app";
import { isShortcutRecordingActive } from "@/lib/format-global-shortcut";

const EMPTY_ATTACHMENTS: ChatAttachment[] = [];
const EMPTY_SUGGESTION_COUNT = 3;

function pickRandomSample<T>(items: T[], count: number): T[] {
  if (items.length <= count) return [...items];
  const copy = [...items];
  for (let i = 0; i < count; i++) {
    const j = i + Math.floor(Math.random() * (copy.length - i));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, count);
}

type ThreadVariant = "default" | "quick";

export function Thread({ variant = "default" }: { variant?: ThreadVariant }) {
  const { t, i18n } = useTranslation();
  const { currentId } = useChat();
  const isQuick = variant === "quick";
  const promptChips = useMemo(() => {
    const all = t("chat.empty.suggestions", { returnObjects: true }) as string[];
    return pickRandomSample(all, EMPTY_SUGGESTION_COUNT);
  }, [currentId, i18n.language, t]);
  const threadKey = currentId ?? "__new__";
  return (
    <ThreadPrimitive.Root key={threadKey} className="flex h-full flex-col">
      <ThreadPrimitive.Viewport className="relative flex-1 overflow-y-auto">
        <ThreadPrimitive.Empty>
          <div
            className="pointer-events-none absolute inset-x-0 top-[8%] z-0 h-[min(55vh,440px)]"
            style={{
              background:
                "radial-gradient(ellipse 680px 68% at 50% 48%, var(--color-brand-soft) 0%, transparent 70%)",
            }}
            aria-hidden
          />
        </ThreadPrimitive.Empty>

        <div
          className={cn(
            "relative z-10 mx-auto w-full py-6",
            isQuick ? "max-w-full px-4 pb-4 pt-8" : "max-w-3xl px-6 py-10",
          )}
        >
          <ThreadPrimitive.Empty>
            <div className="flex min-h-[55vh] flex-col items-center justify-center text-center">
              <h2 className="text-2xl font-semibold tracking-tight">{t("chat.empty.title")}</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                {t("chat.empty.subtitle")}
              </p>
              <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
                {promptChips.map((p) => (
                  <ThreadPrimitive.Suggestion
                    key={p}
                    prompt={p}
                    method="replace"
                    asChild
                  >
                    <button className="rounded-lg border border-border bg-background/80 px-3.5 py-2 text-sm text-muted-foreground shadow-xs transition-all duration-150 hover:border-border hover:bg-surface hover:text-foreground hover:shadow-sm">
                      {p}
                    </button>
                  </ThreadPrimitive.Suggestion>
                ))}
              </div>
            </div>
          </ThreadPrimitive.Empty>

          <ThreadPrimitive.Messages
            components={{
              UserMessage,
              AssistantMessage,
            }}
          />
        </div>

        <ThreadPrimitive.ScrollToBottom asChild>
          {!isQuick ? (
            <Button
              variant="secondary"
              size="icon"
              className="sticky bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-lg transition-opacity disabled:pointer-events-none disabled:opacity-0"
              aria-label={t("chat.composer.scrollToBottom")}
            >
              <ArrowDown />
            </Button>
          ) : (
            <span className="hidden" aria-hidden />
          )}
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Viewport>

      <Composer variant={variant} />
    </ThreadPrimitive.Root>
  );
}

const LONG_PASTE_THRESHOLD = 8000;

const UserText: TextMessagePartComponent = ({ text }) => <Markdown text={text} />;

function Composer({ variant = "default" }: { variant?: ThreadVariant }) {
  const isQuick = variant === "quick";
  const { t } = useTranslation();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { onCompositionStart, onCompositionEnd, shouldBlockEnter } = useImeEnterGuard();
  const runtime = useThreadRuntime();
  const aui = useAui();
  const toast = useToast();
  const {
    isAddingAttachment,
    addPendingFiles,
    isRunning,
    pendingAttachments,
    removePendingAttachment,
    messageQueue,
    enqueueFromComposer,
    removeQueuedMessage,
    flushQueueHead,
  } = useChat();

  // 全局 "/" 聚焦输入（不在其它输入/可编辑元素中时）
  useGlobalFocusShortcut(inputRef, !isQuick);
  useQuickChatComposerFocus(inputRef, isQuick);

  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (isQuick) return;
    const len = e.clipboardData.getData("text").length;
    if (len > LONG_PASTE_THRESHOLD) {
      toast(t("chat.composer.longPaste", { count: len.toLocaleString() }), "info");
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (shouldBlockEnter(e)) {
      e.preventDefault();
      return;
    }

    if (e.key === "Enter" && !e.shiftKey) {
      const text = inputRef.current?.value ?? "";
      const trimmed = text.trim();
      const hasComposerContent = trimmed.length > 0 || pendingAttachments.length > 0;
      const hasQueue = messageQueue.length > 0;

      if (isRunning) {
        if (hasComposerContent) {
          e.preventDefault();
          if (enqueueFromComposer(text)) {
            aui.composer().setText("");
          }
          return;
        }
        if (hasQueue) {
          e.preventDefault();
          void flushQueueHead();
          return;
        }
        return;
      }

      if (!hasComposerContent && hasQueue) {
        e.preventDefault();
        void flushQueueHead();
        return;
      }
    }

    if (e.key === "Escape") {
      // 生成中按 Esc 取消；否则失焦
      const running = runtime.getState().isRunning;
      if (running) {
        e.preventDefault();
        runtime.cancelRun();
      } else {
        inputRef.current?.blur();
      }
    }
  };

  const onPickFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.currentTarget;
    const selected = input.files ? Array.from(input.files) : [];
    input.value = "";
    if (selected.length === 0) return;
    void addPendingFiles(selected);
  };

  const openFilePicker = () => {
    const input = fileInputRef.current;
    if (!input || isAddingAttachment) return;
    input.value = "";
    input.click();
  };

  return (
    <div className={cn(isQuick ? "px-4 pb-3 pt-1" : "px-6 pb-6 pt-2")}>
      {messageQueue.length > 0 ? (
        <div className={cn("mx-auto mb-2 flex w-full flex-col gap-1.5", !isQuick && "max-w-3xl")}>
          {messageQueue.map((item, index) => (
            <div
              key={item.id}
              className="flex items-start gap-2 rounded-lg border border-border/80 bg-surface/60 px-3 py-2 text-sm shadow-xs"
            >
              <div className="min-w-0 flex-1">
                {index === 0 && isRunning ? (
                  <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    {t("chat.queue.pending")}
                  </p>
                ) : null}
                <p className="line-clamp-3 whitespace-pre-wrap break-words text-foreground/90">
                  {item.requestText ||
                    item.displayAttachments?.map((file) => file.name).join("、") ||
                    t("chat.queue.emptyMessage")}
                </p>
                {item.displayAttachments && item.displayAttachments.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {item.displayAttachments.map((file) => (
                      <span
                        key={file.id}
                        className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-background/70 px-2 py-0.5 text-[11px] text-muted-foreground"
                      >
                        <Paperclip className="size-2.5 shrink-0" />
                        <span className="max-w-40 truncate">{file.name}</span>
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => removeQueuedMessage(item.id)}
                className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
                aria-label={t("chat.composer.removeFromQueue")}
                title={t("chat.composer.removeFromQueue")}
              >
                <X className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      ) : null}

      {pendingAttachments.length > 0 ? (
        <div className={cn("mx-auto mb-2 flex w-full flex-wrap gap-1.5", !isQuick && "max-w-3xl")}>
          {pendingAttachments.map((file) => (
            <span
              key={file.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/80 px-2.5 py-1 text-xs text-muted-foreground shadow-xs"
            >
              <Paperclip className="size-3 shrink-0" />
              <span className="max-w-56 truncate">{file.name}</span>
              {!showsUnparseableBadge({ attachmentId: file.attachmentId, kind: file.kind, processable: file.processable }) ? null : (
                <span className="text-warning">{t("chat.attachment.unparseable")}</span>
              )}
              <button
                type="button"
                onClick={() => removePendingAttachment(file.id)}
                className="inline-flex size-4 items-center justify-center rounded-full transition hover:bg-accent hover:text-foreground"
                aria-label={t("chat.attachment.removeNamed", { name: file.name })}
                title={t("chat.composer.removeAttachment")}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}

      <ComposerPrimitive.Root
        className={cn(
          "mx-auto flex w-full items-end gap-2 rounded-xl border border-border bg-background px-2.5 py-2.5 shadow-sm transition-[box-shadow,border-color] duration-150 focus-within:border-brand/30 focus-within:shadow-[0_0_0_3px_var(--color-ring),var(--shadow-sm)]",
          !isQuick && "max-w-3xl",
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={onPickFiles}
        />
        {/* 附件按钮：移至左侧 */}
        <button
          type="button"
          disabled={isAddingAttachment}
          onClick={openFilePicker}
          className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
          aria-label={t("chat.composer.addAttachment")}
          title={isAddingAttachment ? t("chat.composer.attachmentProcessing") : t("chat.composer.addAttachment")}
        >
          <Paperclip className={cn("size-4", isAddingAttachment && "animate-pulse")} />
        </button>

        <ComposerPrimitive.Input
          ref={inputRef}
          rows={1}
          autoFocus
          spellCheck={false}
          onCompositionStart={onCompositionStart}
          onCompositionEnd={onCompositionEnd}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          placeholder={getAgentComposerPlaceholder()}
          className="max-h-48 flex-1 resize-none bg-transparent py-1 text-sm leading-relaxed outline-none placeholder:text-muted-foreground/60"
        />

        <ThreadPrimitive.If running={false}>
          <ComposerPrimitive.Send asChild>
            <button
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand text-brand-foreground shadow-xs transition-[background,transform,opacity] hover:opacity-90 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
              aria-label={t("chat.composer.send")}
            >
              <ArrowUp className="size-4" />
            </button>
          </ComposerPrimitive.Send>
        </ThreadPrimitive.If>
        <ThreadPrimitive.If running>
          <ComposerPrimitive.Cancel asChild>
            <button
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground shadow-xs transition-colors hover:bg-secondary active:translate-y-px"
              aria-label={t("chat.composer.stop")}
            >
              <Square className="size-3 fill-current" />
            </button>
          </ComposerPrimitive.Cancel>
        </ThreadPrimitive.If>
      </ComposerPrimitive.Root>

      {!isQuick ? (
        <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground/50">
          {isRunning
            ? t("chat.composer.keyboardHint.queue")
            : messageQueue.length > 0
              ? t("chat.composer.keyboardHint.queueWithPending")
              : t("chat.composer.keyboardHint.default")}
        </p>
      ) : null}
    </div>
  );
}

function useQuickChatComposerFocus(
  ref: React.RefObject<HTMLTextAreaElement | null>,
  enabled: boolean,
) {
  useEffect(() => {
    if (!enabled || !isDesktopApp()) return;
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    const onFocus = () => ref.current?.focus();
    void (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      if (cancelled) return;
      unlisten = await listen("quick-chat:focus-composer", onFocus);
    })();
    window.addEventListener("quick-chat:focus-composer", onFocus);
    return () => {
      cancelled = true;
      unlisten?.();
      window.removeEventListener("quick-chat:focus-composer", onFocus);
    };
  }, [enabled, ref]);
}

function useGlobalFocusShortcut(
  ref: React.RefObject<HTMLTextAreaElement | null>,
  enabled = true,
) {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: KeyboardEvent) => {
      if (isShortcutRecordingActive()) return;
      const el = document.activeElement as HTMLElement | null;
      const typing =
        !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [ref, enabled]);
}

function useMessageText(): string {
  return useMessage((m) =>
    m.content.map((c) => (c.type === "text" ? c.text : "")).join("").trim(),
  );
}

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation();
  const [copied, copy] = useCopy();
  return (
    <button
      type="button"
      onClick={() => copy(text)}
      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
      aria-label={t("chat.message.copy")}
      title={t("chat.message.copy")}
    >
      {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
    </button>
  );
}

function isAttachmentDownloadable(meta: {
  id?: string;
  attachmentId?: string;
  kind: string;
  processable: boolean;
}): boolean {
  const aid = String(meta.id ?? meta.attachmentId ?? "");
  if (!aid.startsWith("att_")) return false;
  return meta.kind === "other" || (meta.kind === "image" && !meta.processable);
}

function showsUnparseableBadge(meta: {
  id?: string;
  attachmentId?: string;
  kind: string;
  processable: boolean;
}): boolean {
  if (meta.processable) return false;
  return !isAttachmentDownloadable(meta);
}

function isServerDownloadable(file: ChatAttachment): boolean {
  return isAttachmentDownloadable(file);
}

function attachmentDescription(file: ChatAttachment, t: (key: string) => string): string {
  if (isServerDownloadable(file)) return t("chat.attachment.generic");
  if (!file.processable) return t("chat.attachment.unparseable");
  if (file.kind === "text") return file.truncated ? t("chat.attachment.textTruncated") : t("chat.attachment.text");
  if (file.kind === "image") return t("chat.attachment.image");
  return t("chat.attachment.generic");
}

function attachmentImageSrc(file: ChatAttachment): string | null {
  if (file.kind !== "image") return null;
  if (typeof file.imageDataUrl === "string" && file.imageDataUrl.length > 0) {
    return file.imageDataUrl;
  }
  if (file.id.startsWith("att_")) return attachmentDownloadUrl(file.id);
  return null;
}

function canExportAttachment(file: ChatAttachment | null): boolean {
  if (!file) return false;
  if (isServerDownloadable(file)) return true;
  if (file.kind === "text") return typeof file.text === "string";
  if (file.kind === "image") return attachmentImageSrc(file) !== null;
  return false;
}

function downloadChatAttachment(
  file: ChatAttachment,
  toast: ReturnType<typeof useToast>,
  t: (key: string) => string,
): void {
  if (isServerDownloadable(file)) {
    void downloadAttachment(file.id, file.name).catch((err: unknown) => {
      toast(err instanceof Error ? err.message : t("chat.attachment.downloadFailed"), "error");
    });
    return;
  }
  if (!exportInlineAttachment(file)) {
    toast(t("chat.attachment.exportUnsupported"), "info");
  }
}

function exportInlineAttachment(file: ChatAttachment): boolean {
  if (file.kind === "text") {
    const blob = new Blob([file.text ?? ""], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    triggerDownload(url, file.name || "attachment.txt");
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    return true;
  }
  if (file.kind === "image") {
    const src = attachmentImageSrc(file);
    if (!src) return false;
    if (src.startsWith("data:")) {
      triggerDownload(src, file.name || "attachment");
      return true;
    }
    return false;
  }
  return false;
}

function triggerDownload(url: string, filename: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function MessageAttachmentChips({
  attachments,
  align,
  onSelect,
}: {
  attachments: ChatAttachment[];
  align: "start" | "end";
  onSelect: (file: ChatAttachment) => void;
}) {
  const { t } = useTranslation();
  if (attachments.length === 0) return null;
  return (
    <div
      className={cn(
        "mt-1.5 flex flex-wrap gap-1.5",
        align === "end" ? "max-w-[80%] justify-end" : "justify-start",
      )}
    >
      {attachments.map((file) => (
        <button
          type="button"
          key={file.id}
          onClick={() => onSelect(file)}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/70 px-2.5 py-1 text-xs text-muted-foreground transition hover:bg-surface"
          title={t("chat.attachment.viewNamed", { name: file.name })}
        >
          <Paperclip className="size-3" />
          <span className="max-w-56 truncate">{file.name}</span>
          {!showsUnparseableBadge(file) ? null : (
            <span className="text-warning">{t("chat.attachment.unparseable")}</span>
          )}
        </button>
      ))}
    </div>
  );
}

function useAttachmentSelect() {
  const [selectedAttachment, setSelectedAttachment] = useState<ChatAttachment | null>(null);

  const selectAttachment = (file: ChatAttachment) => {
    setSelectedAttachment(file);
  };

  return { selectedAttachment, setSelectedAttachment, selectAttachment };
}

function inlineAttachmentPreview(file: ChatAttachment): {
  content?: string;
  imageSrc?: string | null;
} {
  if (file.kind === "text" && typeof file.text === "string") {
    return { content: file.text };
  }
  if (file.kind === "image") {
    return { imageSrc: attachmentImageSrc(file) };
  }
  return {};
}

function useAttachmentPreview(file: ChatAttachment | null) {
  const { t } = useTranslation();
  const [remote, setRemote] = useState<{
    content?: string;
    imageSrc?: string;
    mimeType?: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setRemote(null);
    setLoading(false);
    setLoadError(null);
    if (!file) return;

    const inline = inlineAttachmentPreview(file);
    if (inline.content !== undefined || inline.imageSrc) return;

    if (!file.id.startsWith("att_") || !isFilePreviewable(file.name, file.mimeType)) return;

    let cancelled = false;
    setLoading(true);
    void fetchAttachmentPreview(file.id, file.name, file.mimeType)
      .then((payload) => {
        if (cancelled) {
          if (payload?.imageSrc) URL.revokeObjectURL(payload.imageSrc);
          return;
        }
        setRemote(payload);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : t("chat.attachment.readFailed"));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [file, t]);

  useEffect(() => {
    const imageSrc = remote?.imageSrc;
    return () => {
      if (imageSrc) URL.revokeObjectURL(imageSrc);
    };
  }, [remote?.imageSrc]);

  if (!file) {
    return { loading: false, loadError: null, content: undefined, imageSrc: null, mimeType: undefined, truncated: false };
  }

  const inline = inlineAttachmentPreview(file);
  return {
    loading,
    loadError,
    content: inline.content ?? remote?.content,
    imageSrc: inline.imageSrc ?? remote?.imageSrc ?? null,
    mimeType: file.mimeType ?? remote?.mimeType,
    truncated: !!file.truncated,
  };
}

function AttachmentDrawer({
  file,
  onClose,
}: {
  file: ChatAttachment | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const preview = useAttachmentPreview(file);
  const previewable = file ? isFilePreviewable(file.name, preview.mimeType ?? file.mimeType) : false;
  const hasPreviewData =
    typeof preview.content === "string" || Boolean(preview.imageSrc);

  return (
    <Drawer
      open={!!file}
      onClose={onClose}
      title={file?.name}
      description={file ? attachmentDescription(file, t) : undefined}
      actions={
        <Button
          variant="ghost"
          size="sm"
          disabled={!canExportAttachment(file)}
          onClick={() => {
            if (!file) return;
            downloadChatAttachment(file, toast, t);
          }}
          title={t("chat.attachment.download")}
          aria-label={t("chat.attachment.download")}
        >
          <Download className="size-4" />
        </Button>
      }
    >
      {file ? (
        preview.loading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : hasPreviewData ? (
          <FilePreview
            filename={file.name}
            content={preview.content}
            imageSrc={preview.imageSrc}
            mimeType={preview.mimeType}
            emptyText={t("chat.attachment.emptyFile")}
            unsupportedText={
              file.kind === "image" && !preview.imageSrc
                ? t("chat.attachment.imageMissingData")
                : t("chat.attachment.previewUnsupported")
            }
            truncated={preview.truncated}
            truncatedText={t("chat.attachment.truncatedDisplay")}
          />
        ) : preview.loadError ? (
          <p className="text-sm text-muted-foreground">{preview.loadError}</p>
        ) : previewable || isServerDownloadable(file) ? (
          <p className="text-sm text-muted-foreground">{t("chat.attachment.previewUnsupported")}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            {file.unsupportedReason || t("chat.attachment.parseUnsupported")}
          </p>
        )
      ) : null}
    </Drawer>
  );
}

const messageMetaRowClass =
  "flex items-center gap-2 opacity-100 transition md:opacity-0 md:group-hover:opacity-100";

function MessageRoleLabel() {
  const { t } = useTranslation();
  return (
    <span className="text-[11px] font-medium tracking-wide text-muted-foreground">{t("chat.message.userLabel")}</span>
  );
}

function MessageTimestamp({ iso }: { iso?: string }) {
  const { formatFull, formatMessageTime } = useTimeFormatters();
  if (!iso) return null;
  return (
    <time
      dateTime={iso}
      title={formatFull(iso)}
      className="text-[11px] tabular-nums text-muted-foreground/75"
    >
      {formatMessageTime(iso)}
    </time>
  );
}

function UserMessage() {
  const { t } = useTranslation();
  const { messageAttachments, messages } = useChat();
  const text = useMessageText();
  const messageId = useMessage((m) => String(m.id ?? ""));
  const chatMsg = messages.find((m) => m.id === messageId);
  const archived = useMessage((m) => (m.metadata as { archived?: boolean } | undefined)?.archived);
  const attachments = messageAttachments[messageId] ?? EMPTY_ATTACHMENTS;
  const { selectedAttachment, setSelectedAttachment, selectAttachment } = useAttachmentSelect();
  const hasText = text.length > 0;
  return (
    <MessagePrimitive.Root
      className={cn("group mb-6 flex flex-col items-end gap-1 text-sm apod-enter-up", archived && "opacity-55")}
    >
      {archived ? (
        <p className="text-[11px] text-muted-foreground">{t("chat.message.archived")}</p>
      ) : (
        <MessageRoleLabel />
      )}
      {hasText ? (
        <div className="min-w-0 max-w-[85%] rounded-xl border border-border bg-surface px-4 py-3 shadow-xs">
          <MessagePrimitive.Parts components={{ Text: UserText }} />
        </div>
      ) : null}
      <MessageAttachmentChips
        attachments={attachments}
        align="end"
        onSelect={selectAttachment}
      />
      <AttachmentDrawer file={selectedAttachment} onClose={() => setSelectedAttachment(null)} />
      <div className={cn(messageMetaRowClass, "justify-end")}>
        <MessageTimestamp iso={chatMsg?.createdAt} />
        <CopyButton text={text} />
      </div>
    </MessagePrimitive.Root>
  );
}

function resolveTodoPlan(
  fromParts: TodoPlan | null,
  sessionTodoPlan: TodoPlan | null,
  isLastAssistant: boolean,
  hasTodoInMessage: boolean,
): TodoPlan | null {
  if (!isLastAssistant) {
    return fromParts ? applyHistoricalTodoInterrupt(fromParts) : null;
  }
  if (!hasTodoInMessage && !fromParts && !sessionTodoPlan) return null;
  if (sessionTodoPlan && fromParts && sessionTodoPlan.plan_id === fromParts.plan_id) {
    return sessionTodoPlan;
  }
  if (fromParts) return fromParts;
  if (hasTodoInMessage && sessionTodoPlan) return sessionTodoPlan;
  return null;
}

function AssistantPartList({
  chatMsg,
  streaming,
  sessionTodoPlan,
  isLastAssistant,
  hideTodo = false,
}: {
  chatMsg: ChatMessage | undefined;
  streaming: boolean;
  sessionTodoPlan: TodoPlan | null;
  isLastAssistant: boolean;
  hideTodo?: boolean;
}) {
  if (!chatMsg) return null;
  const fromParts = extractLatestTodoPlan(chatMsg.parts);
  const hasTodoInMessage = chatMsg.parts.some(
    (p) => p.type === "tool" && isTodoTool(p.toolName) && (p.running || Boolean(p.preview)),
  );
  const todoPlan = resolveTodoPlan(fromParts, sessionTodoPlan, isLastAssistant, hasTodoInMessage);
  const todoToolRunning = chatMsg.parts.some(
    (p) => p.type === "tool" && isTodoTool(p.toolName) && p.running,
  );
  const todoActive =
    Boolean(todoPlan) &&
    (todoPlan!.steps.some((s) => s.status === "in_progress") || todoToolRunning);
  return (
    <>
      {chatMsg.parts.map((p, i) => {
        const isActiveThinking =
          streaming &&
          p.type === "thinking" &&
          !p.completed &&
          i === chatMsg.parts.length - 1;
        if (p.type === "thinking") {
          return (
            <ThinkingBlock
              key={`think-${i}`}
              blockId={`${chatMsg.id}-think-${i}`}
              content={p.text}
              isActive={isActiveThinking}
            />
          );
        }
        if (p.type === "text") {
          if (!p.text) return null;
          return <Markdown key={`text-${i}`} text={p.text} />;
        }
        return <ToolPartView key={p.id} part={p} />;
      })}
      {chatMsg.error ? <Markdown text={`\n\n> ⚠ ${chatMsg.error}`} /> : null}
      {streaming ? <span className="apod-caret mt-0.5" aria-hidden /> : null}
      {!hideTodo && todoPlan ? <TodoProgressPanel plan={todoPlan} active={todoActive} /> : null}
    </>
  );
}

function AssistantMessage() {
  const { t } = useTranslation();
  const { regenerate, canRegenerate, lastErrored, messages, isRunning, messageAttachments, sessionTodoPlan } =
    useChat();
  const id = useMessage((m) => m.id);
  const chatMsg = messages.find((m) => m.id === id);
  const attachments = messageAttachments[id] ?? EMPTY_ATTACHMENTS;
  const { selectedAttachment, setSelectedAttachment, selectAttachment } = useAttachmentSelect();
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const streaming = isRunning && lastAssistant?.id === id;
  const isLastAssistant = lastAssistant?.id === id;
  const text = useMessageText();
  const archived = useMessage((m) => (m.metadata as { archived?: boolean } | undefined)?.archived);
  return (
    <MessagePrimitive.Root className={cn("group mb-6 flex flex-col gap-1 text-sm apod-enter-up", archived && "opacity-55")}>
      {archived ? (
        <p className="text-[11px] text-muted-foreground">{t("chat.message.archived")}</p>
      ) : null}
      <div className="min-w-0">
        <AssistantPartList
          chatMsg={chatMsg}
          streaming={streaming}
          sessionTodoPlan={sessionTodoPlan}
          isLastAssistant={isLastAssistant}
        />
      </div>
      <MessageAttachmentChips
        attachments={attachments}
        align="start"
        onSelect={selectAttachment}
      />
      <AttachmentDrawer file={selectedAttachment} onClose={() => setSelectedAttachment(null)} />

      <MessagePrimitive.If last>
        {lastErrored ? (
          <ThreadPrimitive.If running={false}>
            <button
              type="button"
              onClick={regenerate}
              className="mt-1 inline-flex w-fit items-center gap-1.5 rounded-lg border border-destructive/40 bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive transition hover:bg-destructive/15"
            >
              <RotateCcw className="size-3.5" /> {t("chat.message.retry")}
            </button>
          </ThreadPrimitive.If>
        ) : null}
      </MessagePrimitive.If>

      <ThreadPrimitive.If running={false}>
        <div className={messageMetaRowClass}>
          <MessageTimestamp iso={chatMsg?.createdAt} />
          <CopyButton text={text} />
          <MessagePrimitive.If last>
            <button
              type="button"
              onClick={regenerate}
              disabled={!canRegenerate}
              className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground disabled:opacity-40"
              aria-label={t("chat.message.regenerate")}
              title={t("chat.message.regenerate")}
            >
              <RotateCcw className="size-3.5" />
            </button>
          </MessagePrimitive.If>
        </div>
      </ThreadPrimitive.If>
    </MessagePrimitive.Root>
  );
}
