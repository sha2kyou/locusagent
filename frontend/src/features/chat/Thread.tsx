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
import {
  AGENT_COMPOSER_PLACEHOLDER,
} from "@/lib/agent-status-copy";
import { Markdown, ThinkingBlock } from "./Markdown";
import type { ChatMessage } from "./model";
import { ToolPartView } from "./ToolEvent";
import { extractLatestTodoPlan, applyHistoricalTodoInterrupt, isTodoTool, type TodoPlan } from "./todo";
import { TodoProgressPanel } from "./TodoProgressPanel";
import { useChat } from "./ChatProvider";
import type { ChatAttachment } from "./model";
import { downloadAttachment } from "@/api/endpoints";
import { Drawer } from "@/components/ui/drawer";
import { formatFull, formatMessageTime } from "@/lib/format-time";

const PROMPT_CHIPS = [
  "帮我总结这个网页的要点：sidefyapp.com",
  "AgentPod 有哪些功能？",
  "什么是正态分布概率密度公式？",
  "搜索并总结最新的 AI 进展",
];
const EMPTY_ATTACHMENTS: ChatAttachment[] = [];

const UserText: TextMessagePartComponent = ({ text }) => <Markdown text={text} />;

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col">
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

        <div className="relative z-10 mx-auto w-full max-w-3xl px-6 py-10">
          <ThreadPrimitive.Empty>
            <div className="flex min-h-[55vh] flex-col items-center justify-center text-center">
              <h2 className="text-2xl font-semibold tracking-tight">有什么可以帮你？</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                AgentPod 可读写文件、调用工具、检索网页、记忆与回忆。
              </p>
              <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
                  {PROMPT_CHIPS.map((p) => (
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

      <Composer />
    </ThreadPrimitive.Root>
  );
}

const LONG_PASTE_THRESHOLD = 8000;

function Composer() {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { onCompositionStart, onCompositionEnd, shouldBlockEnter } = useImeEnterGuard();
  const runtime = useThreadRuntime();
  const toast = useToast();
  const { addPendingFiles, isRunning, pendingAttachments, removePendingAttachment } =
    useChat();

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
    <div className="px-6 pb-6 pt-2">
      {pendingAttachments.length > 0 ? (
        <div className="mx-auto mb-2 flex w-full max-w-3xl flex-wrap gap-1.5">
          {pendingAttachments.map((file) => (
            <span
              key={file.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/80 px-2.5 py-1 text-xs text-muted-foreground shadow-xs"
            >
              <Paperclip className="size-3 shrink-0" />
              <span className="max-w-56 truncate">{file.name}</span>
              {!file.processable ? <span className="text-warning">不可解析</span> : null}
              <button
                type="button"
                onClick={() => removePendingAttachment(file.id)}
                className="inline-flex size-4 items-center justify-center rounded-full transition hover:bg-accent hover:text-foreground"
                aria-label={`移除 ${file.name}`}
                title="移除附件"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}

      <ComposerPrimitive.Root className="mx-auto flex w-full max-w-3xl items-end gap-2 rounded-xl border border-border bg-background px-2.5 py-2.5 shadow-sm transition-[box-shadow,border-color] duration-150 focus-within:border-brand/30 focus-within:shadow-[0_0_0_3px_var(--color-ring),var(--shadow-sm)]">
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
          onClick={() => fileInputRef.current?.click()}
          disabled={isRunning}
          className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
          aria-label="添加附件"
          title="添加附件"
        >
          <Paperclip className="size-4" />
        </button>

        <ComposerPrimitive.Input
          ref={inputRef}
          rows={1}
          autoFocus
          onCompositionStart={onCompositionStart}
          onCompositionEnd={onCompositionEnd}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          placeholder={AGENT_COMPOSER_PLACEHOLDER}
          className="max-h-48 flex-1 resize-none bg-transparent py-1 text-sm leading-relaxed outline-none placeholder:text-muted-foreground/60"
        />

        <ThreadPrimitive.If running={false}>
          <ComposerPrimitive.Send asChild>
            <button
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand text-brand-foreground shadow-xs transition-[background,transform,opacity] hover:opacity-90 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="发送"
            >
              <ArrowUp className="size-4" />
            </button>
          </ComposerPrimitive.Send>
        </ThreadPrimitive.If>
        <ThreadPrimitive.If running>
          <ComposerPrimitive.Cancel asChild>
            <button
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground shadow-xs transition-colors hover:bg-secondary active:translate-y-px"
              aria-label="停止"
            >
              <Square className="size-3 fill-current" />
            </button>
          </ComposerPrimitive.Cancel>
        </ThreadPrimitive.If>
      </ComposerPrimitive.Root>

      <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground/50">
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

function isServerDownloadable(file: ChatAttachment): boolean {
  return file.kind === "other" && !file.processable && file.id.startsWith("att_");
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

function exportInlineAttachment(file: ChatAttachment): boolean {
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

function MessageAttachmentChips({
  attachments,
  align,
  onSelect,
}: {
  attachments: ChatAttachment[];
  align: "start" | "end";
  onSelect: (file: ChatAttachment) => void;
}) {
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
          title={isServerDownloadable(file) ? `下载 ${file.name}` : `查看 ${file.name}`}
        >
          {isServerDownloadable(file) ? (
            <Download className="size-3" />
          ) : (
            <Paperclip className="size-3" />
          )}
          <span className="max-w-56 truncate">{file.name}</span>
          {!file.processable && !isServerDownloadable(file) ? (
            <span className="text-warning">不可解析</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

function useAttachmentSelect() {
  const toast = useToast();
  const [selectedAttachment, setSelectedAttachment] = useState<ChatAttachment | null>(null);

  const selectAttachment = (file: ChatAttachment) => {
    if (isServerDownloadable(file)) {
      void downloadAttachment(file.id, file.name).catch((err: unknown) => {
        toast(err instanceof Error ? err.message : "下载失败", "error");
      });
      return;
    }
    setSelectedAttachment(file);
  };

  return { selectedAttachment, setSelectedAttachment, selectAttachment };
}

function AttachmentDrawer({
  file,
  onClose,
}: {
  file: ChatAttachment | null;
  onClose: () => void;
}) {
  const toast = useToast();
  return (
    <Drawer
      open={!!file}
      onClose={onClose}
      title={file?.name}
      description={file ? attachmentDescription(file) : undefined}
      actions={
        <Button
          variant="ghost"
          size="sm"
          disabled={!canExportAttachment(file)}
          onClick={() => {
            if (!file) return;
            const exported = exportInlineAttachment(file);
            if (!exported) {
              toast("当前附件暂不支持导出", "info");
            }
          }}
          title="下载"
          aria-label="下载"
        >
          <Download className="size-4" />
        </Button>
      }
    >
      {file ? (
        <div className="space-y-4">
          {file.processable && file.kind === "text" ? (
            <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-mono text-xs text-foreground">
              {file.text || "（空文件）"}
            </pre>
          ) : file.processable && file.kind === "image" ? (
            file.imageDataUrl ? (
              <div className="max-h-[65vh] overflow-auto rounded-md bg-surface-2 p-2">
                <img
                  src={file.imageDataUrl}
                  alt={file.name}
                  className="mx-auto max-h-[60vh] w-auto max-w-full rounded object-contain"
                />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">图片附件缺少可渲染数据。</p>
            )
          ) : (
            <p className="text-sm text-muted-foreground">
              {file.processable
                ? "该附件类型暂不支持预览。"
                : file.unsupportedReason || "该附件当前不可解析，无法展示内容。"}
            </p>
          )}
          {file.truncated ? <p className="text-xs text-warning">附件内容过长，已截断显示。</p> : null}
        </div>
      ) : null}
    </Drawer>
  );
}

const messageMetaRowClass =
  "flex items-center gap-2 opacity-100 transition md:opacity-0 md:group-hover:opacity-100";

function MessageRoleLabel() {
  return (
    <span className="text-[11px] font-medium tracking-wide text-muted-foreground">你</span>
  );
}

function MessageTimestamp({ iso }: { iso?: string }) {
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
        <p className="text-[11px] text-muted-foreground">已压缩（不再带入上下文）</p>
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
}: {
  chatMsg: ChatMessage | undefined;
  streaming: boolean;
  sessionTodoPlan: TodoPlan | null;
  isLastAssistant: boolean;
}) {
  if (!chatMsg) return null;
  const fromParts = extractLatestTodoPlan(chatMsg.parts);
  const hasTodoInMessage = chatMsg.parts.some(
    (p) => p.type === "tool" && isTodoTool(p.toolName) && (p.running || Boolean(p.preview)),
  );
  const todoPlan = resolveTodoPlan(fromParts, sessionTodoPlan, isLastAssistant, hasTodoInMessage);
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
      {todoPlan ? <TodoProgressPanel plan={todoPlan} /> : null}
    </>
  );
}

function AssistantMessage() {
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
        <p className="text-[11px] text-muted-foreground">已压缩（不再带入上下文）</p>
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
        <div className={messageMetaRowClass}>
          <MessageTimestamp iso={chatMsg?.createdAt} />
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
