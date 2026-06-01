import { useEffect, useRef, useState } from "react";
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useMessage,
  useThreadRuntime,
  type TextMessagePartComponent,
} from "@assistant-ui/react";
import { ArrowDown, ArrowUp, Check, Copy, Download, Paperclip, RotateCcw, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useCopy } from "@/lib/useCopy";
import { Markdown } from "./Markdown";
import { ToolEvent } from "./ToolEvent";
import { useChat } from "./ChatProvider";
import { useShell } from "@/app/AppShell";
import type { ChatAttachment } from "./model";
import { Drawer } from "@/components/ui/drawer";

const PROMPT_CHIPS = [
  "帮我总结这个网页的要点",
  "用 Python 写一个快速排序",
  "记住：我偏好简洁的回答",
];
const EMPTY_ATTACHMENTS: ChatAttachment[] = [];

const MarkdownText: TextMessagePartComponent = ({ text }) => <Markdown text={text} />;

const UserText: TextMessagePartComponent = ({ text }) => (
  <span className="whitespace-pre-wrap">{text}</span>
);

export function Thread() {
  const { readiness } = useChat();
  const { openSettings } = useShell();
  const blocked = readiness.tone === "blocked";

  return (
    <ThreadPrimitive.Root className="flex h-full flex-col">
      <ThreadPrimitive.Viewport className="relative flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          <ThreadPrimitive.Empty>
            <div className="flex min-h-[55vh] flex-col items-center justify-center text-center">
              <h2 className="text-2xl font-semibold tracking-tight">有什么可以帮你？</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Agent 可读写文件、调用工具、检索网页、记忆与回忆。
              </p>
              {blocked ? (
                <Button variant="primary" className="mt-5" onClick={openSettings}>
                  去配置模型
                </Button>
              ) : (
                <div className="mt-6 flex flex-wrap justify-center gap-2">
                  {PROMPT_CHIPS.map((p) => (
                    <ThreadPrimitive.Suggestion
                      key={p}
                      prompt={p}
                      method="replace"
                      asChild
                    >
                      <button className="rounded-full border border-border bg-surface/60 px-3.5 py-1.5 text-sm text-muted-foreground transition hover:border-border-strong hover:text-foreground">
                        {p}
                      </button>
                    </ThreadPrimitive.Suggestion>
                  ))}
                </div>
              )}
            </div>
          </ThreadPrimitive.Empty>

          <ThreadPrimitive.Messages
            components={{ UserMessage, AssistantMessage }}
          />
        </div>

        <ThreadPrimitive.ScrollToBottom asChild>
          <Button
            variant="secondary"
            size="icon"
            className="sticky bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-lg transition-opacity disabled:pointer-events-none disabled:opacity-0"
            aria-label="滚动到底部"
          >
            <ArrowDown />
          </Button>
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Viewport>

      <AgentStatusBar />
      <Composer blocked={blocked} />
    </ThreadPrimitive.Root>
  );
}

function AgentStatusBar() {
  const { readiness } = useChat();
  const r = readiness.reason;
  if (r !== "creating" && r !== "paused" && r !== "stopped" && r !== "failed") return null;

  const config = {
    creating: { text: "Agent 正在启动，请稍候…", cls: "border-warning/30 bg-warning/10 text-warning", pulse: true },
    paused: { text: "Agent 已休眠，发送消息将自动唤醒。", cls: "border-border bg-surface/60 text-muted-foreground", pulse: false },
    stopped: { text: "Agent 已停止，发送消息将重新启动。", cls: "border-border bg-surface/60 text-muted-foreground", pulse: false },
    failed: { text: "Agent 部署失败，请前往设置重试。", cls: "border-destructive/40 bg-destructive/10 text-destructive", pulse: false },
  }[r];

  return (
    <div className="px-4 pt-2">
      <div
        className={cn(
          "mx-auto flex w-full max-w-3xl items-center gap-2 rounded-lg border px-3 py-1.5 text-xs",
          config.cls,
        )}
      >
        <span className={cn("size-1.5 shrink-0 rounded-full bg-current", config.pulse && "animate-pulse")} />
        {config.text}
      </div>
    </div>
  );
}

const LONG_PASTE_THRESHOLD = 8000;

function Composer({ blocked }: { blocked: boolean }) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const runtime = useThreadRuntime();
  const toast = useToast();
  const {
    addPendingFiles,
    isRunning,
    pendingAttachments,
    removePendingAttachment,
  } = useChat();

  // 全局 "/" 聚焦输入（不在其它输入/可编辑元素中时）
  useGlobalFocusShortcut(inputRef);

  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const len = e.clipboardData.getData("text").length;
    if (len > LONG_PASTE_THRESHOLD) {
      toast(`已粘贴较长文本（${len.toLocaleString()} 字符）`, "info");
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
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

  const onPickFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    await addPendingFiles(files);
    e.currentTarget.value = "";
  };

  return (
    <div className="bg-background/80 px-4 py-3 backdrop-blur">
      {pendingAttachments.length > 0 ? (
        <div className="mx-auto mb-2 flex w-full max-w-3xl flex-wrap gap-1.5">
          {pendingAttachments.map((file) => (
            <span
              key={file.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/70 px-2.5 py-1 text-xs text-muted-foreground"
            >
              <Paperclip className="size-3" />
              <span className="max-w-56 truncate">{file.name}</span>
              {!file.processable ? <span className="text-warning">不可解析</span> : null}
              <button
                type="button"
                onClick={() => removePendingAttachment(file.id)}
                className="inline-flex size-4 items-center justify-center rounded-full hover:bg-accent hover:text-foreground"
                aria-label={`移除 ${file.name}`}
                title="移除附件"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <ComposerPrimitive.Root className="mx-auto flex w-full max-w-3xl items-end gap-2 rounded-2xl border border-border-strong bg-surface px-3 py-2 focus-within:border-brand/50">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={onPickFiles}
        />
        <ComposerPrimitive.Input
          ref={inputRef}
          rows={1}
          autoFocus
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          placeholder={blocked ? "请先在设置中配置模型…" : "给 Agent 发送消息…"}
          className="max-h-48 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted-foreground"
        />
        <Button
          type="button"
          variant="primary"
          size="icon"
          className="rounded-xl"
          aria-label="添加附件"
          title="添加附件"
          onClick={() => fileInputRef.current?.click()}
          disabled={isRunning}
        >
          <Paperclip />
        </Button>
        <ThreadPrimitive.If running={false}>
          <ComposerPrimitive.Send asChild>
            <Button variant="primary" size="icon" className="rounded-xl" aria-label="发送">
              <ArrowUp />
            </Button>
          </ComposerPrimitive.Send>
        </ThreadPrimitive.If>
        <ThreadPrimitive.If running>
          <ComposerPrimitive.Cancel asChild>
            <Button variant="secondary" size="icon" className="rounded-xl" aria-label="停止">
              <Square className="size-3.5 fill-current" />
            </Button>
          </ComposerPrimitive.Cancel>
        </ThreadPrimitive.If>
      </ComposerPrimitive.Root>
      <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-muted-foreground/60">
        Enter 发送 · Shift+Enter 换行 · 一次 1 个附件（支持文本与图片）
        <ThreadPrimitive.If running>
          <span> · Esc 停止</span>
        </ThreadPrimitive.If>
      </p>
    </div>
  );
}

function useGlobalFocusShortcut(ref: React.RefObject<HTMLTextAreaElement | null>) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
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
  }, [ref]);
}

function useMessageText(): string {
  return useMessage((m) =>
    m.content.map((c) => (c.type === "text" ? c.text : "")).join("").trim(),
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, copy] = useCopy();
  return (
    <button
      type="button"
      onClick={() => copy(text)}
      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
      aria-label="复制"
      title="复制"
    >
      {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
    </button>
  );
}

function UserMessage() {
  const toast = useToast();
  const text = useMessageText();
  const archived = useMessage((m) => (m.metadata as { archived?: boolean } | undefined)?.archived);
  const rawAttachments = useMessage(
    (m) => (m.metadata as { attachments?: ChatAttachment[] } | undefined)?.attachments,
  );
  const attachments = rawAttachments ?? EMPTY_ATTACHMENTS;
  const [selectedAttachment, setSelectedAttachment] = useState<ChatAttachment | null>(null);
  const hasText = text.length > 0;
  return (
    <MessagePrimitive.Root className="group mb-5 flex flex-col items-end">
      {hasText || archived ? (
        <div
          className={cn(
            "max-w-[80%] rounded-2xl rounded-br-sm bg-secondary px-4 py-2.5 text-sm",
            archived && "opacity-55",
          )}
        >
          {archived ? (
            <p className="mb-1 text-[11px] text-muted-foreground">已压缩（不再带入上下文）</p>
          ) : null}
          <MessagePrimitive.Parts components={{ Text: UserText }} />
        </div>
      ) : null}
      {attachments.length > 0 ? (
        <div className="mt-1.5 flex max-w-[80%] flex-wrap justify-end gap-1.5">
          {attachments.map((file) => (
            <button
              type="button"
              key={file.id}
              onClick={() => setSelectedAttachment(file)}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/70 px-2.5 py-1 text-xs text-muted-foreground transition hover:border-border-strong hover:bg-surface"
              title={`查看 ${file.name} 内容`}
            >
              <Paperclip className="size-3" />
              <span className="max-w-56 truncate">{file.name}</span>
              {!file.processable ? <span className="text-warning">不可解析</span> : null}
            </button>
          ))}
        </div>
      ) : null}
      <Drawer
        open={!!selectedAttachment}
        onClose={() => setSelectedAttachment(null)}
        title={selectedAttachment?.name}
        description={selectedAttachment ? attachmentDescription(selectedAttachment) : undefined}
        actions={
          <Button
            variant="ghost"
            size="sm"
            disabled={!canExportAttachment(selectedAttachment)}
            onClick={() => {
              if (!selectedAttachment) return;
              const exported = exportAttachment(selectedAttachment);
              if (!exported) {
                toast("当前附件暂不支持导出", "info");
              }
            }}
            title="导出"
            aria-label="导出"
          >
            <Download className="size-4" />
          </Button>
        }
        width="xl"
      >
        {selectedAttachment ? (
          <div className="space-y-4">
            {selectedAttachment.processable && selectedAttachment.kind === "text" ? (
              <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-mono text-xs text-foreground">
                {selectedAttachment.text || "（空文件）"}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">
                {selectedAttachment.processable
                  ? "该附件不是文本类型，当前仅支持查看文本附件内容。"
                  : selectedAttachment.unsupportedReason || "该附件当前不可解析，无法展示内容。"}
              </p>
            )}
            {selectedAttachment.truncated ? (
              <p className="text-xs text-warning">附件内容过长，已截断显示。</p>
            ) : null}
          </div>
        ) : null}
      </Drawer>
      <div className="mt-0.5 opacity-100 transition md:opacity-0 md:group-hover:opacity-100">
        <CopyButton text={text} />
      </div>
    </MessagePrimitive.Root>
  );
}

function attachmentDescription(file: ChatAttachment): string {
  if (!file.processable) return "不可解析";
  if (file.kind === "text") return file.truncated ? "文本附件（已截断）" : "文本附件";
  if (file.kind === "image") return "图片附件";
  return "附件";
}

function canExportAttachment(file: ChatAttachment | null): boolean {
  if (!file) return false;
  if (file.kind === "text") return typeof file.text === "string";
  if (file.kind === "image") return typeof file.imageDataUrl === "string" && file.imageDataUrl.length > 0;
  return false;
}

function exportAttachment(file: ChatAttachment): boolean {
  if (file.kind === "text") {
    const blob = new Blob([file.text ?? ""], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    triggerDownload(url, file.name || "attachment.txt");
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    return true;
  }
  if (file.kind === "image" && file.imageDataUrl) {
    triggerDownload(file.imageDataUrl, file.name || "attachment");
    return true;
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

function AssistantMessage() {
  const { regenerate, canRegenerate, lastErrored } = useChat();
  const text = useMessageText();
  const archived = useMessage((m) => (m.metadata as { archived?: boolean } | undefined)?.archived);
  return (
    <MessagePrimitive.Root className={cn("group mb-6 flex flex-col gap-1 text-sm", archived && "opacity-55")}>
      {archived ? (
        <p className="text-[11px] text-muted-foreground">已压缩（不再带入上下文）</p>
      ) : null}
      <div className="min-w-0">
        <MessagePrimitive.Parts
          components={{ Text: MarkdownText, tools: { Fallback: ToolEvent } }}
        />
      </div>
      <MessagePrimitive.If last>
        <ThreadPrimitive.If running>
          <span className="apod-caret mt-0.5" aria-hidden />
        </ThreadPrimitive.If>
      </MessagePrimitive.If>

      <MessagePrimitive.If last>
        {lastErrored ? (
          <ThreadPrimitive.If running={false}>
            <button
              type="button"
              onClick={regenerate}
              className="mt-1 inline-flex w-fit items-center gap-1.5 rounded-lg border border-destructive/40 bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive transition hover:bg-destructive/15"
            >
              <RotateCcw className="size-3.5" /> 重试
            </button>
          </ThreadPrimitive.If>
        ) : null}
      </MessagePrimitive.If>

      <ThreadPrimitive.If running={false}>
        <div className="flex items-center gap-0.5 opacity-100 transition md:opacity-0 md:group-hover:opacity-100">
          <CopyButton text={text} />
          <MessagePrimitive.If last>
            <button
              type="button"
              onClick={regenerate}
              disabled={!canRegenerate}
              className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground disabled:opacity-40"
              aria-label="重新生成"
              title="重新生成"
            >
              <RotateCcw className="size-3.5" />
            </button>
          </MessagePrimitive.If>
        </div>
      </ThreadPrimitive.If>
    </MessagePrimitive.Root>
  );
}
