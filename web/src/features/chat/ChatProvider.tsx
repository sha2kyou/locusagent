import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import {
  cancelRun,
  createAttachment as apiCreateAttachment,
  deleteSession as apiDeleteSession,
  getActiveRun,
  getSessionMessages,
  listSessions,
} from "@/api/endpoints";
import type { SessionMeta } from "@/api/types";
import { ApiError } from "@/api/client";
import { streamChatCompletion } from "@/api/stream";
import { formatStreamRetryToast, userMessageFromContainerError } from "@/lib/agent-status-copy";
import { toastAction } from "@/lib/toast-copy";
import { useToast } from "@/components/ui/toast";
import { useAuth, type AgentReadiness } from "@/app/auth";
import { withWorkspacePrefix } from "@/app/workspace-route";
import {
  appendText,
  appendThinking,
  completeThinkingParts,
  type ChatAttachment,
  type ChatMessage,
  type ChatPart,
  emptyAssistant,
  uid,
  userMessage,
} from "./model";
import { convertMessage } from "./convert";
import { coalesceHistory, historyPollKey } from "./history";

export interface PendingAttachment {
  id: string;
  attachmentId: string;
  name: string;
  size: number;
  kind: "text" | "image" | "other";
  mimeType?: string;
  text?: string;
  imageDataUrl?: string;
  processable: boolean;
  unsupportedReason?: string;
  truncated: boolean;
}

interface ChatContextValue {
  messages: ChatMessage[];
  sessions: SessionMeta[];
  loadingSessions: boolean;
  currentId: string | null;
  query: string;
  setQuery: (q: string) => void;
  readiness: AgentReadiness;
  isRunning: boolean;
  lastErrored: boolean;
  canRegenerate: boolean;
  messageAttachments: Record<string, ChatAttachment[]>;
  pendingAttachments: PendingAttachment[];
  addPendingFiles: (files: FileList | File[]) => Promise<void>;
  removePendingAttachment: (id: string) => void;
  clearPendingAttachments: () => void;
  send: (text: string) => void;
  regenerate: () => void;
  newSession: () => void;
  selectSession: (id: string) => void;
  deleteSession: (id: string, options?: { silent?: boolean }) => Promise<void>;
}

const ChatContext = createContext<ChatContextValue | null>(null);
export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}

const DEFAULT_TITLE = "新对话";
const DEFAULT_MAX_FILE_SIZE = 1024 * 1024;
const MAX_TOTAL_ATTACHMENTS = 1;
const MAX_ATTACHMENT_CHARS = 16000;
const IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"];
type ChatRequestContent =
  | string
  | ({ type: "text"; text: string } | { type: "image_url"; image_url: { url: string } })[];

function isImageInputUnsupportedError(err: unknown): boolean {
  if (!err || typeof err !== "object") return false;
  const msg = String((err as { message?: unknown }).message ?? "");
  const code = String((err as { code?: unknown }).code ?? "");
  const detail = (err as { detail?: unknown }).detail;
  const detailText =
    typeof detail === "string" ? detail : detail == null ? "" : JSON.stringify(detail);
  const joined = `${msg}\n${detailText}`.toLowerCase();
  return (
    code === "404" &&
    (joined.includes("support image input") ||
      joined.includes("no endpoints found that support image input"))
  );
}

function chatPath(sessionId: string | null, workspaceId?: string | null): string {
  const base = sessionId ? `/chat/${encodeURIComponent(sessionId)}` : "/chat";
  return withWorkspacePrefix(base, workspaceId);
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const { readiness, me, reload } = useAuth();
  const navigate = useNavigate();
  const params = useParams();
  const urlSessionId = params.sessionId ?? null;
  const urlWorkspaceId = params.workspaceId ?? null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [lastErrored, setLastErrored] = useState(false);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const messageAttachments = useMemo<Record<string, ChatAttachment[]>>(() => {
    const map: Record<string, ChatAttachment[]> = {};
    for (const msg of messages) {
      if (msg.role !== "user" || !msg.attachments?.length) continue;
      map[msg.id] = msg.attachments;
    }
    return map;
  }, [messages]);

  const currentIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pollTokenRef = useRef(0);
  const pendingAttachmentsRef = useRef<PendingAttachment[]>([]);
  const mountedRef = useRef(true);
  const titlePollTimerRef = useRef<number | null>(null);
  const prevUrlSessionRef = useRef<string | null | undefined>(undefined);
  const loadTokenRef = useRef(0);

  useEffect(() => {
    pendingAttachmentsRef.current = pendingAttachments;
  }, [pendingAttachments]);

  // 发送消息触发容器唤醒时，加快刷新就绪状态以便状态栏自动消失
  useEffect(() => {
    if (!isRunning) return;
    const waking =
      readiness.reason === "paused" ||
      readiness.reason === "stopped" ||
      readiness.reason === "creating";
    if (!waking) return;

    void reload();
    const id = window.setInterval(() => void reload(), 1500);
    return () => clearInterval(id);
  }, [isRunning, readiness.reason, reload]);

  const setCurrent = (id: string | null) => {
    currentIdRef.current = id;
    setCurrentId(id);
  };

  // ---- 会话列表 ----
  const refreshSessions = async (): Promise<SessionMeta[]> => {
    try {
      const { items } = await listSessions();
      items.sort((a, b) => (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at));
      if (mountedRef.current) setSessions(items);
      return items;
    } catch {
      /* 容器未就绪等：忽略，由就绪提示兜底 */
      return [];
    } finally {
      if (mountedRef.current) setLoadingSessions(false);
    }
  };

  useEffect(() => {
    void refreshSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- 流式辅助：更新最后一条 assistant ----
  const updateLastAssistant = (fn: (parts: ChatPart[]) => ChatPart[], error?: string) => {
    setMessages((prev) => {
      const idx = lastAssistantIndex(prev);
      if (idx < 0) return prev;
      const m = prev[idx];
      const next = { ...m, parts: fn(m.parts), error: error ?? m.error };
      return [...prev.slice(0, idx), next, ...prev.slice(idx + 1)];
    });
  };

  const stopRunningTools = (reason: string) => {
    updateLastAssistant((parts) =>
      parts.map((p) =>
        p.type === "tool" && p.running
          ? { ...p, running: false, preview: p.preview ?? reason, elapsedMs: p.startedAt ? Date.now() - p.startedAt : undefined }
          : p,
      ),
    );
  };

  const abortChat = () => {
    abortRef.current?.abort();
    abortRef.current = null;
  };

  const stopTitlePoll = () => {
    if (titlePollTimerRef.current !== null) {
      window.clearInterval(titlePollTimerRef.current);
      titlePollTimerRef.current = null;
    }
  };

  // ---- 标题自动生成轮询 ----
  const watchTitle = (sid: string) => {
    stopTitlePoll();
    let tries = 0;
    const timer = window.setInterval(async () => {
      if (!mountedRef.current) {
        stopTitlePoll();
        return;
      }
      tries += 1;
      const items = await refreshSessions();
      const found = items.find((s) => s.id === sid);
      if (tries >= 12 || (found && found.title && found.title !== DEFAULT_TITLE)) {
        clearInterval(timer);
        titlePollTimerRef.current = null;
      }
    }, 2500);
    titlePollTimerRef.current = timer;
  };

  // ---- active-run 轮询恢复 ----
  const startActiveRunPoll = (sid: string) => {
    const token = ++pollTokenRef.current;
    setIsRunning(true);
    let lastKey = "";
    const tick = async () => {
      if (token !== pollTokenRef.current) return;
      try {
        const { run } = await getActiveRun(sid);
        const { items } = await getSessionMessages(sid);
        const live = run?.status === "running";
        const key = historyPollKey(items);
        if (key !== lastKey) {
          lastKey = key;
          setMessages(coalesceHistory(items, { live }));
        }
        if (live) {
          if (token === pollTokenRef.current) window.setTimeout(tick, 2000);
        } else {
          setIsRunning(false);
        }
      } catch {
        setIsRunning(false);
      }
    };
    void tick();
  };

  const stopActiveRunPoll = () => {
    pollTokenRef.current++;
  };

  const resetToNewChat = () => {
    abortChat();
    stopActiveRunPoll();
    stopTitlePoll();
    setCurrent(null);
    setMessages([]);
    setIsRunning(false);
    setPendingAttachments([]);
    setLastErrored(false);
  };

  const loadSessionFromUrl = (id: string) => {
    const token = ++loadTokenRef.current;
    abortChat();
    stopActiveRunPoll();
    stopTitlePoll();
    setCurrent(id);
    setIsRunning(false);
    setPendingAttachments([]);
    setLastErrored(false);
    void (async () => {
      try {
        const [{ items }, { run }] = await Promise.all([
          getSessionMessages(id),
          getActiveRun(id),
        ]);
        if (token !== loadTokenRef.current || !mountedRef.current || currentIdRef.current !== id) {
          return;
        }
        const live = run?.status === "running";
        setMessages(coalesceHistory(items, { live }));
        if (live) {
          setIsRunning(true);
          startActiveRunPoll(id);
        }
      } catch (e) {
        if (token !== loadTokenRef.current || !mountedRef.current) return;
        toast((e as Error).message || "对话不存在", "error");
        resetToNewChat();
        navigate(chatPath(null, urlWorkspaceId), { replace: true });
      }
    })();
  };

  // URL 为会话单一真相源：刷新 / 前进后退 / 侧边栏切换均由此恢复
  useEffect(() => {
    const prev = prevUrlSessionRef.current;
    prevUrlSessionRef.current = urlSessionId;

    if (urlSessionId) {
      if (currentIdRef.current === urlSessionId && messages.length > 0) return;
      loadSessionFromUrl(urlSessionId);
      return;
    }

    if (prev !== undefined) resetToNewChat();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlSessionId]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
      pollTokenRef.current++;
      if (titlePollTimerRef.current !== null) {
        window.clearInterval(titlePollTimerRef.current);
        titlePollTimerRef.current = null;
      }
    };
  }, []);

  // ---- 发送 / 重跑 ----
  // appendUser=false 用于"重新生成 / 重试"：复用最后一条用户消息重跑，
  // 后端在 new_user == 库内最后一条 user 时不会重复落库（见 v1._prepare_messages）。
  const runTurn = async (
    text: string,
    opts: {
      appendUser: boolean;
      requestText?: string;
      requestContent?: ChatRequestContent;
      displayAttachments?: ChatAttachment[];
      attachmentIds?: string[];
    },
  ) => {
    const wakingOnSend =
      readiness.reason === "paused" || readiness.reason === "stopped";
    if (wakingOnSend) {
      void reload();
    }
    abortChat();
    setLastErrored(false);
    setMessages((prev) => {
      if (opts.appendUser) {
        return [
          ...prev,
          userMessage(text, opts.requestText ?? text, opts.displayAttachments),
          emptyAssistant(),
        ];
      }
      const arr = [...prev];
      while (arr.length && arr[arr.length - 1].role === "assistant") arr.pop();
      return [...arr, emptyAssistant()];
    });
    setIsRunning(true);

    const ac = new AbortController();
    abortRef.current = ac;

    const sid = currentIdRef.current;
    const body = {
      messages: [
        {
          role: "user",
          content: opts.requestContent ?? opts.requestText ?? text,
          ...(opts.attachmentIds?.length ? { attachment_ids: opts.attachmentIds } : {}),
        },
      ],
      stream: true as const,
      ...(sid ? { session_id: sid } : {}),
    };

    let firstToken = true;
    let handoffToPoll = false;
    try {
      await streamChatCompletion(
        body,
        {
          onMessage: (chunk) => {
            if (!mountedRef.current || ac.signal.aborted) return;
            if (chunk.session_id) {
              if (!currentIdRef.current) setCurrent(chunk.session_id);
              const path = chatPath(chunk.session_id, urlWorkspaceId);
              if (window.location.pathname !== path) {
                navigate(path, { replace: true });
              }
              void refreshSessions();
              watchTitle(chunk.session_id);
            }
            const ev = chunk.x_event;
            if (ev === "tool_call") {
              updateLastAssistant((parts) => [
                ...completeThinkingParts(parts),
                {
                  type: "tool",
                  id: chunk.x_tool_id || chunk.x_tool_call_id || uid("t"),
                  toolName: chunk.x_tool_name || "tool",
                  toolKind: chunk.x_tool_kind || "tool",
                  running: true,
                  startedAt: Date.now(),
                },
              ]);
            } else if (ev === "tool_result") {
              const id = chunk.x_tool_call_id || chunk.x_tool_id;
              const preview = chunk.x_preview;
              updateLastAssistant((parts) => {
                let done = false;
                const mapped = parts.map((p) => {
                  if (!done && p.type === "tool" && p.running && (!id || p.id === id)) {
                    done = true;
                    return {
                      ...p,
                      running: false,
                      preview,
                      toolName: chunk.x_tool_name || p.toolName,
                      elapsedMs: p.startedAt ? Date.now() - p.startedAt : undefined,
                    };
                  }
                  return p;
                });
                if (!done && preview) {
                  mapped.push({
                    type: "tool",
                    id: id || uid("t"),
                    toolName: chunk.x_tool_name || "tool",
                    toolKind: chunk.x_tool_kind || "tool",
                    running: false,
                    preview,
                    startedAt: 0,
                  });
                }
                return mapped;
              });
            } else if (ev === "error") {
              updateLastAssistant((p) => p, chunk.x_message || "出错了");
            } else {
              const delta = chunk.choices?.[0]?.delta;
              const reasoning = delta?.reasoning_content;
              const content = delta?.content;
              if (reasoning) {
                updateLastAssistant((parts) => appendThinking(parts, reasoning));
              }
              if (content) {
                firstToken = false;
                updateLastAssistant((parts) => appendText(parts, content));
              }
            }
          },
          onRetry: (attempt, sec) => {
            toast(formatStreamRetryToast(attempt, sec, wakingOnSend), "info");
          },
        },
        { signal: ac.signal },
      );
    } catch (e) {
      const err = e as { code?: string; message?: string; status?: number };
      if (ac.signal.aborted) {
        if (firstToken) updateLastAssistant((p) => appendText(p, "（已停止生成）"));
      } else if (err.code === "run_in_progress") {
        toast("该对话仍在生成中", "info");
        if (mountedRef.current && currentIdRef.current) {
          handoffToPoll = true;
          startActiveRunPoll(currentIdRef.current);
        }
        return;
      } else if (isImageInputUnsupportedError(err)) {
        const tip = "当前模型或上游端点不支持图片输入，请切换支持视觉的模型后重试。";
        updateLastAssistant((p) => p, tip);
        toast(tip, "error");
        setLastErrored(true);
      } else {
        const status = e instanceof ApiError ? e.status : err.status;
        const code = e instanceof ApiError ? e.code : err.code;
        const friendly = userMessageFromContainerError(code, status);
        const message =
          friendly || (e instanceof Error ? e.message : undefined) || "请求失败";
        updateLastAssistant((p) => p, message);
        setLastErrored(true);
      }
    } finally {
      if (abortRef.current === ac) abortRef.current = null;
      if (!mountedRef.current) return;
      if (!handoffToPoll) {
        updateLastAssistant((parts) => completeThinkingParts(parts));
        setIsRunning(false);
      }
      void refreshSessions();
    }
  };

  const send = (
    text: string,
    requestText?: string,
    requestContent?: ChatRequestContent,
    displayAttachments?: ChatAttachment[],
    attachmentIds?: string[],
  ) => runTurn(text, { appendUser: true, requestText, requestContent, displayAttachments, attachmentIds });

  const regenerate = () => {
    if (isRunning) return;
    const lastInput = lastUserInput(messages);
    if (!lastInput) return;
    void runTurn(lastInput.text, {
      appendUser: false,
      requestText: lastInput.text,
      requestContent: lastInput.text,
      attachmentIds: lastInput.attachmentIds,
    });
  };

  const cancel = async () => {
    abortChat();
    stopActiveRunPoll();
    stopRunningTools("已停止");
    updateLastAssistant((parts) => completeThinkingParts(parts));
    setIsRunning(false);
    const sid = currentIdRef.current;
    if (sid) await cancelRun(sid).catch(() => {});
  };

  // ---- 会话操作 ----
  const newSession = () => {
    navigate(chatPath(null, urlWorkspaceId));
  };

  const selectSession = (id: string) => {
    navigate(chatPath(id, urlWorkspaceId));
  };

  // toast 放在 Provider：删除当前对话会触发路由 remount，Sidebar 层调用不可靠
  const deleteSession = async (id: string, options?: { silent?: boolean }) => {
    const raw = sessions.find((s) => s.id === id)?.title ?? "";
    const title = raw.trim() || DEFAULT_TITLE;
    const wasCurrent = currentIdRef.current === id || urlSessionId === id;
    if (wasCurrent) {
      abortChat();
      stopActiveRunPoll();
    }
    await apiDeleteSession(id);
    if (!options?.silent) {
      toast(toastAction("已删除", title, "对话"), "success");
    }
    if (!mountedRef.current) return;
    await refreshSessions();
    if (wasCurrent && mountedRef.current) navigate(chatPath(null, urlWorkspaceId));
  };

  const removePendingAttachment = (id: string) => {
    setPendingAttachments((prev) => prev.filter((item) => item.id !== id));
  };

  const clearPendingAttachments = () => {
    setPendingAttachments([]);
  };

  const addPendingFiles = async (files: FileList | File[]) => {
    const maxFileSize = normalizeAttachmentMaxBytes(me?.attachment_max_bytes);
    const current = pendingAttachmentsRef.current;
    const remain = MAX_TOTAL_ATTACHMENTS - current.length;
    const selected = Array.from(files).slice(0, 1);
    if (selected.length === 0) return;
    if (Array.from(files).length > 1) {
      toast("一次仅支持添加 1 个附件", "info");
    }
    const next: PendingAttachment[] = [];
    for (const file of selected) {
      if (file.size > maxFileSize) {
        toast(`${file.name} 超过 ${formatBytes(maxFileSize)}，已跳过`, "error");
        continue;
      }
      try {
        if (isProcessableTextFile(file)) {
          const raw = await file.text();
          const normalized = raw.replace(/\r\n/g, "\n");
          const truncated = normalized.length > MAX_ATTACHMENT_CHARS;
          const textContent = truncated
            ? `${normalized.slice(0, MAX_ATTACHMENT_CHARS)}\n...（文件过长，已截断）`
            : normalized;
          const created = await apiCreateAttachment({
            session_id: currentIdRef.current,
            name: file.name,
            size_bytes: file.size,
            kind: "text",
            mime_type: file.type || "text/plain",
            text_content: textContent,
            processable: true,
            truncated,
          });
          next.push({
            id: uid("f"),
            attachmentId: created.id,
            name: created.name,
            size: file.size,
            kind: "text",
            text: created.text,
            processable: created.processable,
            truncated: !!created.truncated,
          });
        } else if (isImageFile(file)) {
          const imageDataUrl = await fileToDataUrl(file);
          const created = await apiCreateAttachment({
            session_id: currentIdRef.current,
            name: file.name,
            size_bytes: file.size,
            kind: "image",
            mime_type: file.type || guessMimeTypeByName(file.name) || "image/png",
            image_data_url: imageDataUrl,
            processable: true,
            truncated: false,
          });
          next.push({
            id: uid("f"),
            attachmentId: created.id,
            name: created.name,
            size: file.size,
            kind: "image",
            mimeType: created.mimeType,
            imageDataUrl: created.imageDataUrl,
            processable: created.processable,
            truncated: false,
          });
        } else {
          const created = await apiCreateAttachment({
            session_id: currentIdRef.current,
            name: file.name,
            size_bytes: file.size,
            kind: "other",
            mime_type: file.type || undefined,
            processable: false,
            unsupported_reason: "当前仅支持文本或图片附件",
            truncated: false,
          });
          next.push({
            id: uid("f"),
            attachmentId: created.id,
            name: created.name,
            size: file.size,
            kind: "other",
            processable: false,
            unsupportedReason: created.unsupportedReason ?? "当前仅支持文本或图片附件",
            truncated: false,
          });
        }
      } catch {
        toast(`${file.name} 读取失败，请重试`, "error");
      }
    }
    if (next.length > 0) {
      if (remain <= 0) {
        toast("已替换为新附件", "info");
      }
      setPendingAttachments(next);
    }
  };

  const runtime = useExternalStoreRuntime({
    isRunning,
    messages,
    convertMessage,
    isSendDisabled: !readiness.ready,
    onNew: async (m) => {
      const text = m.content
        .map((c) => (c.type === "text" ? c.text : ""))
        .join("")
        .trim();
      const attachments = pendingAttachmentsRef.current;
      if (!text && attachments.length === 0) return;
      const displayText = buildDisplayText(text, attachments);
      const requestText = text.trim();
      const requestContent = text.trim();
      const displayAttachments = buildDisplayAttachments(attachments);
      const attachmentIds = attachments.map((file) => file.attachmentId);
      clearPendingAttachments();
      await send(displayText, requestText, requestContent, displayAttachments, attachmentIds);
    },
    onCancel: cancel,
  });

  return (
    <ChatContext.Provider
      value={{
        messages,
        sessions,
        loadingSessions,
        currentId,
        query,
        setQuery,
        readiness,
        isRunning,
        lastErrored,
        canRegenerate: !isRunning && messages.some((m) => m.role === "user"),
        messageAttachments,
        pendingAttachments,
        addPendingFiles,
        removePendingAttachment,
        clearPendingAttachments,
        send: (text: string) => {
          void send(text);
        },
        regenerate,
        newSession,
        selectSession,
        deleteSession,
      }}
    >
      <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
    </ChatContext.Provider>
  );
}

function lastAssistantIndex(msgs: ChatMessage[]): number {
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "assistant") return i;
  }
  return -1;
}

function lastUserInput(msgs: ChatMessage[]): { text: string; attachmentIds: string[] } | null {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const msg = msgs[i];
    if (msg.role !== "user") continue;
    const text = (
      msg.sourceText ??
      msg.parts.map((p) => (p.type === "text" ? p.text : "")).join("")
    ).trim();
    const attachmentIds = (msg.attachments ?? [])
      .map((a) => String(a.id || "").trim())
      .filter((id) => id.length > 0);
    if (text || attachmentIds.length > 0) {
      return { text, attachmentIds };
    }
  }
  return null;
}

function buildDisplayText(text: string, attachments: PendingAttachment[]): string {
  const clean = text.trim();
  if (attachments.length === 0) return clean;
  return clean;
}

function buildDisplayAttachments(attachments: PendingAttachment[]): ChatAttachment[] | undefined {
  if (attachments.length === 0) return undefined;
  return attachments.map((file) => ({
    id: file.attachmentId,
    name: file.name,
    kind: file.kind,
    mimeType: file.mimeType,
    text: file.kind === "text" ? file.text : undefined,
    imageDataUrl: file.kind === "image" ? file.imageDataUrl : undefined,
    processable: file.processable,
    unsupportedReason: file.unsupportedReason,
    truncated: file.truncated,
  }));
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size}B`;
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)}MB`;
  return `${(size / 1024).toFixed(1)}KB`;
}

function normalizeAttachmentMaxBytes(value: number | null | undefined): number {
  const n = Number(value);
  if (Number.isFinite(n) && n >= 64 * 1024) {
    return Math.floor(n);
  }
  return DEFAULT_MAX_FILE_SIZE;
}

function isProcessableTextFile(file: File): boolean {
  if (file.type.startsWith("text/")) return true;
  const lower = file.name.toLowerCase();
  const textExts = [
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".csv",
    ".log",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
    ".sql",
  ];
  return textExts.some((ext) => lower.endsWith(ext));
}

function isImageFile(file: File): boolean {
  if (file.type.startsWith("image/")) return true;
  const lower = file.name.toLowerCase();
  return IMAGE_EXTS.some((ext) => lower.endsWith(ext));
}

function guessMimeTypeByName(name: string): string | undefined {
  const lower = name.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".bmp")) return "image/bmp";
  if (lower.endsWith(".svg")) return "image/svg+xml";
  return undefined;
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result === "string" && result.startsWith("data:")) {
        resolve(result);
        return;
      }
      reject(new Error("invalid file reader result"));
    };
    reader.onerror = () => reject(reader.error ?? new Error("file reader failed"));
    reader.readAsDataURL(file);
  });
}
