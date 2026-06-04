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
import { useImeEnterGuard } from "@/lib/ime-enter";
import { useCopy } from "@/lib/useCopy";
import { ProvisionRetryButton } from "@/components/ProvisionRetry";
import {
  AGENT_COMPOSER_FAILED,
  AGENT_COMPOSER_NOT_READY,
  AGENT_COMPOSER_PLACEHOLDER,
  AGENT_PAUSED,
  AGENT_STARTING,
  AGENT_STOPPED,
  PROVISION_FAILED_HINT,
  PROVISION_FAILED_STATUS,
} from "@/lib/agent-status-copy";
import { Markdown, ProseMarkdown, ThinkingBlock } from "./Markdown";
import type { ChatMessage } from "./model";
import { ToolPartView } from "./ToolEvent";
import { useChat } from "./ChatProvider";
import type { ChatAttachment } from "./model";
import { Drawer } from "@/components/ui/drawer";

const PROMPT_CHIPS = [
  "帮我总结这个网页的要点：sidefyapp.com",
  "AgentPod 有哪些功能？",
  "什么是正态分布概率密度公式？",
  "搜索并总结最新的 AI 进展",
];
const EMPTY_ATTACHMENTS: ChatAttachment[] = [];

const UserText: TextMessagePartComponent = ({ text }) => (
  <ProseMarkdown text={text} className="[&_p]:my-0" />
);

export function Thread() {
  const { readiness } = useChat();
  const failed = readiness.reason === "failed";
  const booting = readiness.reason === "creating" || readiness.reason === "absent";

  return (
    <ThreadPrimitive.Root className="flex h-full flex-col">
      <ThreadPrimitive.Viewport className="relative flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          <ThreadPrimitive.Empty>
            <div className="flex min-h-[55vh] flex-col items-center justify-center text-center">
              <h2 className="text-2xl font-semibold tracking-tight">有什么可以帮你？</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                AgentPod 可读写文件、调用工具、检索网页、记忆与回忆。
              </p>
              {failed ? (
                <FailedProvisionPanel className="mt-5" />
              ) : booting ? null : (
                <div className="mt-6 flex flex-col items-center gap-2">
                  {Array.from({ length: Math.ceil(PROMPT_CHIPS.length / 2) }, (_, row) => (
                    <div key={row} className="flex gap-2 justify-center">
                      {PROMPT_CHIPS.slice(row * 2, row * 2 + 2).map((p) => (
                        <ThreadPrimitive.Suggestion
                          key={p}
                          prompt={p}
                          method="replace"
                          asChild
                        >
                          <button className="rounded-xl border border-border bg-surface/60 px-3.5 py-2 text-sm text-muted-foreground transition hover:border-border-strong hover:text-foreground">
                            {p}
                          </button>
                        </ThreadPrimitive.Suggestion>
                      ))}
                    </div>
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
      <Composer />
    </ThreadPrimitive.Root>
  );
}

function FailedProvisionPanel({ className }: { className?: string }) {
  return (
    <div className={cn("flex max-w-md flex-col items-center gap-3 text-sm text-muted-foreground", className)}>
      <p>{PROVISION_FAILED_HINT}</p>
      <ProvisionRetryButton size="md" />
    </div>
  );
}

function AgentStatusBar() {
  const { readiness } = useChat();
  const r = readiness.reason;
  if (r !== "creating" && r !== "paused" && r !== "stopped" && r !== "failed") return null;

  if (r === "failed") {
    return (
      <div className="px-4 pt-2">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <div className="flex items-center gap-2">
            <span className="size-1.5 shrink-0 rounded-full bg-current" />
            <span>{PROVISION_FAILED_STATUS}</span>
          </div>
          <ProvisionRetryButton />
        </div>
      </div>
    );
  }

  const config = {
    creating: { text: AGENT_STARTING, cls: "border-warning/30 bg-warning/10 text-warning", pulse: true },
    paused: { text: AGENT_PAUSED, cls: "border-border bg-surface/60 text-muted-foreground", pulse: false },
    stopped: { text: AGENT_STOPPED, cls: "border-border bg-surface/60 text-muted-foreground", pulse: false },
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

function Composer() {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { onCompositionStart, onCompositionEnd, shouldBlockEnter } = useImeEnterGuard();
  const runtime = useThreadRuntime();
  const toast = useToast();
  const { readiness, addPendingFiles, isRunning, pendingAttachments, removePendingAttachment } =
    useChat();
  const failed = readiness.reason === "failed";
  const notReady = !readiness.ready;

  // 全局 "/" 聚焦输入（不在其它输入/可编辑元素中时）
  useGlobalFocusShortcut(inputRef);

  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const len = e.clipboardData.getData("text").length;
    if (len > LONG_PASTE_THRESHOLD) {
      toast(`已粘贴较长文本（${len.toLocaleString()} 字符）`, "info");
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (shouldBlockEnter(e)) {
      e.preventDefault();
      return;
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
          onCompositionStart={onCompositionStart}
          onCompositionEnd={onCompositionEnd}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          placeholder={
            failed
              ? AGENT_COMPOSER_FAILED
              : notReady
                ? AGENT_COMPOSER_NOT_READY
                : AGENT_COMPOSER_PLACEHOLDER
          }
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
        Enter 发送 · Shift+Enter 换行
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
  const { messageAttachments } = useChat();
  const text = useMessageText();
  const messageId = useMessage((m) => String(m.id ?? ""));
  const archived = useMessage((m) => (m.metadata as { archived?: boolean } | undefined)?.archived);
  const attachments = messageAttachments[messageId] ?? EMPTY_ATTACHMENTS;
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
      >
        {selectedAttachment ? (
          <div className="space-y-4">
            {selectedAttachment.processable && selectedAttachment.kind === "text" ? (
              <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-mono text-xs text-foreground">
                {selectedAttachment.text || "（空文件）"}
              </pre>
            ) : selectedAttachment.processable && selectedAttachment.kind === "image" ? (
              selectedAttachment.imageDataUrl ? (
                <div className="max-h-[65vh] overflow-auto rounded-md bg-surface-2 p-2">
                  <img
                    src={selectedAttachment.imageDataUrl}
                    alt={selectedAttachment.name}
                    className="mx-auto max-h-[60vh] w-auto max-w-full rounded object-contain"
                  />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">图片附件缺少可渲染数据。</p>
              )
            ) : (
              <p className="text-sm text-muted-foreground">
                {selectedAttachment.processable
                  ? "该附件类型暂不支持预览。"
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

function AssistantPartList({
  chatMsg,
  streaming,
}: {
  chatMsg: ChatMessage | undefined;
  streaming: boolean;
}) {
  if (!chatMsg) return null;
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
    </>
  );
}

function AssistantMessage() {
  const { regenerate, canRegenerate, lastErrored, messages, isRunning } = useChat();
  const id = useMessage((m) => m.id);
  const chatMsg = messages.find((m) => m.id === id);
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const streaming = isRunning && lastAssistant?.id === id;
  const text = useMessageText();
  const archived = useMessage((m) => (m.metadata as { archived?: boolean } | undefined)?.archived);
  return (
    <MessagePrimitive.Root className={cn("group mb-6 flex flex-col gap-1 text-sm", archived && "opacity-55")}>
      {archived ? (
        <p className="text-[11px] text-muted-foreground">已压缩（不再带入上下文）</p>
      ) : null}
      <div className="min-w-0">
        <AssistantPartList chatMsg={chatMsg} streaming={streaming} />
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
