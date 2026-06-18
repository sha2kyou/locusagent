import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
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
import { ApiError, getWorkspaceId, setWorkspaceId } from "@/api/client";
import type { ChatChunk } from "@/api/types";
import { streamChatCompletion, streamActiveRun } from "@/api/stream";
import { formatStreamRetryToast, userMessageFromContainerError } from "@/lib/agent-status-copy";
import { sha256HexBytes, bytesToBase64 } from "@/lib/file-digest";
import { toastAction } from "@/lib/toast-copy";
import { displaySessionTitle, isBackendDefaultSessionTitle } from "@/lib/session-title";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/app/auth";
import { withWorkspacePrefix } from "@/app/workspace-route";
import { isNewChatKeyboardShortcut, isShortcutRecordingActive } from "@/lib/format-global-shortcut";
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
import { coalesceHistory } from "./history";
import { mergeStreamSyncParts } from "./stream-sync";
import { isTodoTool, parseTodoPlan, type TodoPlan } from "./todo";
import { formatToolArgsPreview } from "./tool-args";

export interface PendingAttachment {
  id: string;
  attachmentId: string;
  name: string;
  size: number;
  kind: "text" | "image" | "other";
  mimeType?: string;
  text?: string;
  imageDataUrl?: string;
  contentSha256?: string;
  processable: boolean;
  unsupportedReason?: string;
  truncated: boolean;
}

export interface QueuedMessage {
  id: string;
  displayText: string;
  requestText: string;
  requestContent: ChatRequestContent;
  displayAttachments?: ChatAttachment[];
  attachmentIds: string[];
}

interface ChatContextValue {
  messages: ChatMessage[];
  sessions: SessionMeta[];
  loadingSessions: boolean;
  hasMoreSessions: boolean;
  loadingMoreSessions: boolean;
  loadMoreSessions: () => Promise<void>;
  currentId: string | null;
  query: string;
  setQuery: (q: string) => void;
  isRunning: boolean;
  lastErrored: boolean;
  canRegenerate: boolean;
  messageAttachments: Record<string, ChatAttachment[]>;
  pendingAttachments: PendingAttachment[];
  isAddingAttachment: boolean;
  addPendingFiles: (files: FileList | File[]) => Promise<void>;
  removePendingAttachment: (id: string) => void;
  clearPendingAttachments: () => void;
  messageQueue: QueuedMessage[];
  enqueueFromComposer: (text: string) => boolean;
  removeQueuedMessage: (id: string) => void;
  flushQueueHead: () => Promise<void>;
  send: (text: string) => void;
  regenerate: () => void;
  newSession: () => void;
  selectSession: (id: string) => void;
  deleteSession: (id: string, options?: { silent?: boolean }) => Promise<void>;
  sessionTodoPlan: TodoPlan | null;
}

const ChatContext = createContext<ChatContextValue | null>(null);
export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}

const PAGE_SIZE = 10;
const DEFAULT_MAX_FILE_SIZE = 25 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENTS = 1;
const ATTACHMENT_UPLOAD_TIMEOUT_BASE_MS = 60_000;
const ATTACHMENT_UPLOAD_TIMEOUT_MAX_MS = 180_000;
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

const ACTIVE_RUN_ATTACH_MAX_RETRIES = 2;
const ACTIVE_RUN_ATTACH_RETRY_MS = 400;

function ensureLiveAssistant(messages: ChatMessage[]): ChatMessage[] {
  if (messages.some((m) => m.role === "assistant")) return messages;
  return [...messages, emptyAssistant()];
}

function chatPath(
  sessionId: string | null,
  workspaceId?: string | null,
  mode: "default" | "quick" = "default",
): string {
  if (mode === "quick") {
    return sessionId ? `/quick-chat/${encodeURIComponent(sessionId)}` : "/quick-chat";
  }
  const base = sessionId ? `/chat/${encodeURIComponent(sessionId)}` : "/chat";
  return withWorkspacePrefix(base, workspaceId);
}

const ACTIVE_RUN_SETTLE_MS = 200;
const ACTIVE_RUN_SETTLE_TRIES = 15;

async function waitActiveRunSettled(sessionId: string): Promise<void> {
  for (let i = 0; i < ACTIVE_RUN_SETTLE_TRIES; i++) {
    try {
      const { run } = await getActiveRun(sessionId);
      if (run?.status !== "running") return;
    } catch {
      return;
    }
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, ACTIVE_RUN_SETTLE_MS);
    });
  }
}

export function ChatProvider({
  children,
  mode = "default",
}: {
  children: ReactNode;
  mode?: "default" | "quick";
}) {
  const isQuick = mode === "quick";
  const { t } = useTranslation();
  const toast = useToast();
  const { me } = useAuth();
  const navigate = useNavigate();
  const params = useParams();
  const urlSessionId = params.sessionId ?? null;
  const urlWorkspaceId = params.workspaceId ?? null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionTodoPlan, setSessionTodoPlan] = useState<TodoPlan | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [lastErrored, setLastErrored] = useState(false);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [hasMoreSessions, setHasMoreSessions] = useState(false);
  const [loadingMoreSessions, setLoadingMoreSessions] = useState(false);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [isAddingAttachment, setIsAddingAttachment] = useState(false);
  const [messageQueue, setMessageQueue] = useState<QueuedMessage[]>([]);
  const messageQueueRef = useRef<QueuedMessage[]>([]);
  const isRunningRef = useRef(false);
  const tryProcessQueueRef = useRef<() => void>(() => {});
  const messageAttachments = useMemo<Record<string, ChatAttachment[]>>(() => {
    const map: Record<string, ChatAttachment[]> = {};
    for (const msg of messages) {
      if (!msg.attachments?.length) continue;
      map[msg.id] = msg.attachments;
    }
    return map;
  }, [messages]);

  const visibleLimitRef = useRef(PAGE_SIZE);
  const currentIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pollTokenRef = useRef(0);
  const pendingAttachmentsRef = useRef<PendingAttachment[]>([]);
  const attachmentUploadBusyRef = useRef(false);
  const uploadWatchdogRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const titlePollTimerRef = useRef<number | null>(null);
  const prevUrlSessionRef = useRef<string | null | undefined>(undefined);
  const loadTokenRef = useRef(0);
  const pinnedUrlWorkspaceIdRef = useRef<string | null | undefined>(undefined);
  const pinnedWorkspaceIdRef = useRef<string>("");
  const newSessionRef = useRef<() => void>(() => {});

  const resolveChatPath = (sessionId: string | null) => chatPath(sessionId, urlWorkspaceId, mode);

  useLayoutEffect(() => {
    if (isQuick) {
      pinnedWorkspaceIdRef.current =
        me?.current_workspace_id || getWorkspaceId() || "";
      if (pinnedWorkspaceIdRef.current) setWorkspaceId(pinnedWorkspaceIdRef.current);
      return;
    }
    if (pinnedUrlWorkspaceIdRef.current !== undefined) return;
    pinnedUrlWorkspaceIdRef.current = urlWorkspaceId;
    pinnedWorkspaceIdRef.current =
      urlWorkspaceId || me?.current_workspace_id || getWorkspaceId() || "";
    if (pinnedWorkspaceIdRef.current) setWorkspaceId(pinnedWorkspaceIdRef.current);
  }, [urlWorkspaceId, me?.current_workspace_id, isQuick]);

  useEffect(() => {
    if (isQuick) return;
    if (pinnedUrlWorkspaceIdRef.current === undefined) return;
    const pinnedUrl = pinnedUrlWorkspaceIdRef.current;
    const pinnedId = pinnedWorkspaceIdRef.current;
    if (urlWorkspaceId !== pinnedUrl) {
      navigate(chatPath(urlSessionId, pinnedUrl ? pinnedId : null), { replace: true });
      return;
    }
    if (getWorkspaceId() !== pinnedId) setWorkspaceId(pinnedId || undefined);
  }, [urlWorkspaceId, urlSessionId, me?.current_workspace_id, navigate, isQuick]);

  useEffect(() => {
    pendingAttachmentsRef.current = pendingAttachments;
  }, [pendingAttachments]);

  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);

  const clearMessageQueue = () => {
    messageQueueRef.current = [];
    setMessageQueue([]);
  };

  const updateMessageQueue = (updater: (prev: QueuedMessage[]) => QueuedMessage[]) => {
    setMessageQueue((prev) => {
      const next = updater(prev);
      messageQueueRef.current = next;
      return next;
    });
  };

  const setCurrent = (id: string | null) => {
    currentIdRef.current = id;
    setCurrentId(id);
  };

  // ---- 会话列表 ----
  const refreshSessions = async (): Promise<SessionMeta[]> => {
    try {
      const limit = visibleLimitRef.current;
      const { items } = await listSessions(limit + 1);
      const hasMore = items.length > limit;
      const visible = items.slice(0, limit);
      visible.sort((a, b) => (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at));
      if (mountedRef.current) {
        setSessions(visible);
        setHasMoreSessions(hasMore);
      }
      return visible;
    } catch {
      /* 后端未就绪等：忽略，由就绪提示兜底 */
      return [];
    } finally {
      if (mountedRef.current) setLoadingSessions(false);
    }
  };

  const loadMoreSessions = async () => {
    if (loadingMoreSessions) return;
    setLoadingMoreSessions(true);
    visibleLimitRef.current += PAGE_SIZE;
    try {
      await refreshSessions();
    } finally {
      if (mountedRef.current) setLoadingMoreSessions(false);
    }
  };

  useEffect(() => {
    void refreshSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- 流式辅助：更新最后一条 assistant ----
  const updateLastAssistant = (fn: (parts: ChatPart[]) => ChatPart[], error?: string) => {
    setMessages((prev) => {
      let base = prev;
      let idx = lastAssistantIndex(base);
      if (idx < 0) {
        base = [...base, emptyAssistant()];
        idx = base.length - 1;
      }
      const m = base[idx];
      const next = { ...m, parts: fn(m.parts), error: error ?? m.error };
      return [...base.slice(0, idx), next, ...base.slice(idx + 1)];
    });
  };

  /** 流式 delta 单独刷帧，避免 React 18 在同一次 SSE read 内批量合并 setState */
  const updateLastAssistantStream = (fn: (parts: ChatPart[]) => ChatPart[]) => {
    queueMicrotask(() => {
      if (!mountedRef.current) return;
      updateLastAssistant(fn);
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
    const maxTries = 24;
    const tick = async () => {
      if (!mountedRef.current) {
        stopTitlePoll();
        return;
      }
      tries += 1;
      const items = await refreshSessions();
      const found = items.find((s) => s.id === sid);
      if (found && found.title && !isBackendDefaultSessionTitle(found.title)) {
        stopTitlePoll();
        return;
      }
      if (tries >= maxTries) {
        stopTitlePoll();
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 2500);
    titlePollTimerRef.current = timer;
  };

  // ---- 流式事件处理（新请求与 active run 重连共用） ----
  const applyStreamSync = (sync: NonNullable<ChatChunk["x_sync"]>) => {
    const syncId = sync.assistant_message_id != null ? `a_${sync.assistant_message_id}` : undefined;
    setMessages((prev) => {
      const idx = lastAssistantIndex(prev);
      if (idx >= 0) {
        const m = prev[idx];
        const merged = mergeStreamSyncParts(m.parts, sync, { live: true });
        const next = {
          ...m,
          id: syncId ?? m.id,
          parts: merged,
        };
        return [...prev.slice(0, idx), next, ...prev.slice(idx + 1)];
      }
      const merged = mergeStreamSyncParts([], sync, { live: true });
      const assistant: ChatMessage = {
        ...emptyAssistant(),
        ...(syncId ? { id: syncId } : {}),
        parts: merged,
      };
      return [...prev, assistant];
    });
  };

  const resyncLiveSession = async (sid: string) => {
    const [{ items, todo_plan: todoPlan }, { run }] = await Promise.all([
      getSessionMessages(sid),
      getActiveRun(sid),
    ]);
    const live = run?.status === "running";
    setMessages(ensureLiveAssistant(coalesceHistory(items, { live })));
    setSessionTodoPlan(parseTodoPlan(todoPlan));
    return run;
  };

  const applyStreamChunk = (chunk: ChatChunk, opts: { navigateSession?: boolean } = {}) => {
    if (!mountedRef.current) return;
    const navigateSession = opts.navigateSession ?? false;
    if (chunk.session_id && navigateSession) {
      if (!currentIdRef.current) setCurrent(chunk.session_id);
      const path = resolveChatPath(chunk.session_id);
      if (window.location.pathname !== path) {
        navigate(path, { replace: true });
      }
      void refreshSessions();
      watchTitle(chunk.session_id);
    }
    const ev = chunk.x_event;
    if (ev === "sync") {
      if (chunk.x_sync) applyStreamSync(chunk.x_sync);
      return;
    }
    if (ev === "tool_call") {
      const toolId = chunk.x_tool_id || chunk.x_tool_call_id || uid("t");
      updateLastAssistant((parts) => {
        if (parts.some((p) => p.type === "tool" && p.id === toolId)) return parts;
        return [
          ...completeThinkingParts(parts),
          {
            type: "tool",
            id: toolId,
            toolName: chunk.x_tool_name || "tool",
            toolKind: chunk.x_tool_kind || "tool",
            running: true,
            startedAt: Date.now(),
            argsPreview: formatToolArgsPreview(chunk.x_tool_args),
          },
        ];
      });
    } else if (ev === "tool_result") {
      const id = chunk.x_tool_call_id || chunk.x_tool_id;
      const preview = chunk.x_preview;
      const streamElapsedMs =
        typeof chunk.x_elapsed_ms === "number" && chunk.x_elapsed_ms >= 0
          ? chunk.x_elapsed_ms
          : undefined;
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
              elapsedMs:
                streamElapsedMs ?? (p.startedAt ? Date.now() - p.startedAt : undefined),
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
            ...(streamElapsedMs !== undefined ? { elapsedMs: streamElapsedMs } : {}),
          });
        }
        return mapped;
      });
      if (isTodoTool(chunk.x_tool_name || "")) {
        const plan = parseTodoPlan(preview);
        if (plan) setSessionTodoPlan(plan);
      }
    } else if (ev === "attachment") {
      const attId = chunk.x_attachment_id;
      const attName = chunk.x_attachment_name || "file";
      if (!attId) return;
      setMessages((prev) => {
        const next = [...prev];
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role !== "assistant") continue;
          const existing = next[i].attachments ?? [];
          if (existing.some((a) => a.id === attId)) return prev;
          next[i] = {
            ...next[i],
            attachments: [
              ...existing,
              {
                id: attId,
                name: attName,
                kind: "other",
                processable: false,
              },
            ],
          };
          return next;
        }
        return prev;
      });
    } else if (ev === "error") {
      updateLastAssistant((p) => p, chunk.x_message || t("chat.errors.generic"));
    } else {
      const delta = chunk.choices?.[0]?.delta;
      const reasoning = delta?.reasoning_content;
      const content = delta?.content;
      if (reasoning) {
        updateLastAssistantStream((parts) => appendThinking(parts, reasoning));
      }
      if (content) {
        updateLastAssistantStream((parts) => appendText(parts, content));
      }
    }
  };

  // ---- active-run SSE 重连（切页回来后恢复真实流式） ----
  const attachActiveRunStream = (sid: string, runId: string, attempt = 0) => {
    if (attempt > ACTIVE_RUN_ATTACH_MAX_RETRIES) {
      setIsRunning(false);
      return;
    }
    const token = ++pollTokenRef.current;
    abortChat();
    setIsRunning(true);
    const ac = new AbortController();
    abortRef.current = ac;

    void (async () => {
      try {
        await resyncLiveSession(sid);
        if (token !== pollTokenRef.current || !mountedRef.current) return;
        await streamActiveRun(
          sid,
          runId,
          { onMessage: (chunk) => applyStreamChunk(chunk) },
          { signal: ac.signal },
        );
      } catch (e) {
        if (!mountedRef.current || token !== pollTokenRef.current || ac.signal.aborted) return;
        const status = e instanceof ApiError ? e.status : (e as { status?: number }).status;
        if (status === 404 && attempt < ACTIVE_RUN_ATTACH_MAX_RETRIES) {
          await new Promise<void>((resolve) => {
            window.setTimeout(resolve, ACTIVE_RUN_ATTACH_RETRY_MS * (attempt + 1));
          });
          if (token !== pollTokenRef.current || !mountedRef.current) return;
          try {
            const { run } = await getActiveRun(sid);
            if (token !== pollTokenRef.current || !mountedRef.current) return;
            if (run?.status === "running" && run.id) {
              attachActiveRunStream(sid, run.id, attempt + 1);
              return;
            }
            await resyncLiveSession(sid);
          } catch {
            /* 回退加载失败 */
          }
        }
        if (token === pollTokenRef.current) setIsRunning(false);
        return;
      } finally {
        if (!mountedRef.current || token !== pollTokenRef.current) return;
        if (abortRef.current === ac) abortRef.current = null;
        if (!ac.signal.aborted) {
          updateLastAssistant((parts) =>
            completeThinkingParts(parts).map((p) =>
              p.type === "tool" && p.running
                ? {
                    ...p,
                    running: false,
                    elapsedMs: p.elapsedMs ?? (p.startedAt ? Date.now() - p.startedAt : undefined),
                  }
                : p,
            ),
          );
          isRunningRef.current = false;
          setIsRunning(false);
          void refreshSessions();
          watchTitle(sid);
          queueMicrotask(() => {
            tryProcessQueueRef.current();
          });
        }
      }
    })();
  };

  const stopActiveRunAttach = () => {
    pollTokenRef.current++;
    abortChat();
  };

  const resetToNewChat = () => {
    abortChat();
    stopActiveRunAttach();
    stopTitlePoll();
    setCurrent(null);
    setMessages([]);
    setSessionTodoPlan(null);
    isRunningRef.current = false;
    setIsRunning(false);
    setPendingAttachments([]);
    clearMessageQueue();
    setLastErrored(false);
  };

  const loadSessionFromUrl = (id: string) => {
    const token = ++loadTokenRef.current;
    abortChat();
    stopActiveRunAttach();
    stopTitlePoll();
    setCurrent(id);
    isRunningRef.current = false;
    setIsRunning(false);
    setPendingAttachments([]);
    clearMessageQueue();
    setLastErrored(false);
    void (async () => {
      try {
        const [{ items, todo_plan: todoPlan }, { run }] = await Promise.all([
          getSessionMessages(id),
          getActiveRun(id),
        ]);
        if (token !== loadTokenRef.current || !mountedRef.current || currentIdRef.current !== id) {
          return;
        }
        const live = run?.status === "running";
        setMessages(ensureLiveAssistant(coalesceHistory(items, { live })));
        setSessionTodoPlan(parseTodoPlan(todoPlan));
        if (live && run?.id) {
          setIsRunning(true);
          attachActiveRunStream(id, run.id);
        }
      } catch (e) {
        if (token !== loadTokenRef.current || !mountedRef.current) return;
        toast((e as Error).message || t("chat.errors.sessionNotFound"), "error");
        resetToNewChat();
        navigate(resolveChatPath(null), { replace: true });
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
    abortChat();
    setLastErrored(false);
    if (opts.appendUser) {
      setSessionTodoPlan(null);
    }
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
    isRunningRef.current = true;

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
    let handoffToAttach = false;
    let retriedAfterStaleRun = false;
    try {
      for (;;) {
        try {
          await streamChatCompletion(
            body,
            {
              onMessage: (chunk) => {
                if (chunk.choices?.[0]?.delta?.content) firstToken = false;
                applyStreamChunk(chunk, { navigateSession: true });
              },
          onRetry: (attempt, sec) => {
            toast(formatStreamRetryToast(attempt, sec), "info");
          },
        },
        { signal: ac.signal },
          );
          break;
        } catch (inner) {
          const innerErr = inner as { code?: string; message?: string; status?: number };
          const sidForRetry = currentIdRef.current;
          if (
            !retriedAfterStaleRun &&
            innerErr.code === "run_in_progress" &&
            sidForRetry
          ) {
            retriedAfterStaleRun = true;
            await cancelRun(sidForRetry).catch(() => {});
            await waitActiveRunSettled(sidForRetry);
            continue;
          }
          throw inner;
        }
      }
    } catch (e) {
      const err = e as { code?: string; message?: string; status?: number };
      if (ac.signal.aborted) {
        if (firstToken) updateLastAssistant((p) => appendText(p, t("chat.errors.stopped")));
      } else if (err.code === "run_in_progress") {
        toast(t("chat.errors.stillGenerating"), "info");
        const runId = e instanceof ApiError ? String((e.detail as { run_id?: string } | undefined)?.run_id || "") : "";
        if (mountedRef.current && currentIdRef.current) {
          handoffToAttach = true;
          const sid = currentIdRef.current;
          if (runId) {
            attachActiveRunStream(sid, runId);
          } else {
            void getActiveRun(sid).then(({ run }) => {
              if (run?.status === "running" && run.id) attachActiveRunStream(sid, run.id);
            });
          }
        }
        return;
      } else if (isImageInputUnsupportedError(err)) {
        const tip = t("chat.errors.visionUnsupported");
        updateLastAssistant((p) => p, tip);
        toast(tip, "error");
        setLastErrored(true);
      } else {
        const status = e instanceof ApiError ? e.status : err.status;
        const code = e instanceof ApiError ? e.code : err.code;
        const friendly = userMessageFromContainerError(code, status);
        const message =
          friendly || (e instanceof Error ? e.message : undefined) || t("chat.errors.requestFailed");
        updateLastAssistant((p) => p, message);
        setLastErrored(true);
      }
    } finally {
      if (abortRef.current === ac) abortRef.current = null;
      if (!mountedRef.current) return;
      if (!handoffToAttach) {
        updateLastAssistant((parts) =>
          completeThinkingParts(parts).map((p) =>
            p.type === "tool" && p.running
              ? {
                  ...p,
                  running: false,
                  elapsedMs: p.elapsedMs ?? (p.startedAt ? Date.now() - p.startedAt : undefined),
                }
              : p,
          ),
        );
        // 用户主动中断时由 cancel() 在后端收敛后再置 false，避免可发送但 run 仍 active
        if (!ac.signal.aborted) {
          isRunningRef.current = false;
          setIsRunning(false);
          const sidAfterRun = currentIdRef.current;
          if (sidAfterRun) {
            void getActiveRun(sidAfterRun)
              .then(({ run }) => {
                if (!mountedRef.current || currentIdRef.current !== sidAfterRun) return;
                if (run?.status === "running" && run.id) attachActiveRunStream(sidAfterRun, run.id);
              })
              .catch(() => {});
          }
          queueMicrotask(() => {
            tryProcessQueueRef.current();
          });
        }
      }
      void refreshSessions();
      const sidAfter = currentIdRef.current;
      if (sidAfter) watchTitle(sidAfter);
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
    stopActiveRunAttach();
    stopRunningTools(t("chat.errors.toolsStopped"));
    updateLastAssistant((parts) => completeThinkingParts(parts));

    const sid = currentIdRef.current;
    if (sid) {
      try {
        await cancelRun(sid);
        await waitActiveRunSettled(sid);
      } catch {
        /* 忽略取消失败 */
      }
    }
    setIsRunning(false);
    isRunningRef.current = false;
  };

  const sendQueuedMessage = (item: QueuedMessage) => {
    void runTurn(item.displayText, {
      appendUser: true,
      requestText: item.requestText,
      requestContent: item.requestContent,
      displayAttachments: item.displayAttachments,
      attachmentIds: item.attachmentIds,
    });
  };

  const tryProcessQueue = () => {
    const item = messageQueueRef.current[0];
    if (!item || isRunningRef.current) return;
    updateMessageQueue((prev) => prev.slice(1));
    sendQueuedMessage(item);
  };

  tryProcessQueueRef.current = tryProcessQueue;

  const buildQueuedMessage = (text: string): QueuedMessage | null => {
    const attachments = pendingAttachmentsRef.current;
    const requestText = text.trim();
    if (!requestText && attachments.length === 0) return null;
    const displayText = buildDisplayText(requestText, attachments);
    const displayAttachments = buildDisplayAttachments(attachments);
    const attachmentIds = attachments.map((file) => file.attachmentId);
    return {
      id: uid("q"),
      displayText,
      requestText,
      requestContent: requestText,
      displayAttachments,
      attachmentIds,
    };
  };

  const enqueueFromComposer = (text: string): boolean => {
    const item = buildQueuedMessage(text);
    if (!item) return false;
    updateMessageQueue((prev) => [...prev, item]);
    clearPendingAttachments();
    return true;
  };

  const removeQueuedMessage = (id: string) => {
    updateMessageQueue((prev) => prev.filter((item) => item.id !== id));
  };

  const flushQueueHead = async () => {
    const item = messageQueueRef.current[0];
    if (!item) return;
    updateMessageQueue((prev) => prev.slice(1));
    if (isRunningRef.current) {
      await cancel();
    }
    sendQueuedMessage(item);
  };

  // ---- 会话操作 ----
  const newSession = () => {
    if (isQuick) {
      resetToNewChat();
      navigate("/quick-chat", { replace: true });
      return;
    }
    resetToNewChat();
    navigate(resolveChatPath(null), { replace: true });
  };
  newSessionRef.current = newSession;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isShortcutRecordingActive()) return;
      if (!isNewChatKeyboardShortcut(event)) return;
      event.preventDefault();
      newSessionRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const selectSession = (id: string) => {
    navigate(resolveChatPath(id));
  };

  // toast 放在 Provider：删除当前对话会触发路由 remount，Sidebar 层调用不可靠
  const deleteSession = async (id: string, options?: { silent?: boolean }) => {
    const raw = sessions.find((s) => s.id === id)?.title ?? "";
    const title = displaySessionTitle(raw, t);
    const wasCurrent = currentIdRef.current === id || urlSessionId === id;
    if (wasCurrent) {
      abortChat();
      stopActiveRunAttach();
    }
    await apiDeleteSession(id);
    if (!options?.silent) {
      toast(toastAction("deleted", title, "session"), "success");
    }
    if (!mountedRef.current) return;
    await refreshSessions();
    if (wasCurrent && mountedRef.current) navigate(resolveChatPath(null));
  };

  const removePendingAttachment = (id: string) => {
    setPendingAttachments((prev) => prev.filter((item) => item.id !== id));
    endAttachmentUpload();
  };

  const clearPendingAttachments = () => {
    setPendingAttachments([]);
  };

  const clearUploadWatchdog = () => {
    if (uploadWatchdogRef.current !== null) {
      window.clearTimeout(uploadWatchdogRef.current);
      uploadWatchdogRef.current = null;
    }
  };

  const beginAttachmentUpload = () => {
    attachmentUploadBusyRef.current = true;
    clearUploadWatchdog();
    setIsAddingAttachment(true);
    uploadWatchdogRef.current = window.setTimeout(() => {
      attachmentUploadBusyRef.current = false;
      setIsAddingAttachment(false);
      uploadWatchdogRef.current = null;
    }, ATTACHMENT_UPLOAD_TIMEOUT_MAX_MS + 10_000);
  };

  const endAttachmentUpload = () => {
    attachmentUploadBusyRef.current = false;
    clearUploadWatchdog();
    setIsAddingAttachment(false);
  };

  const processPendingFiles = async (files: FileList | File[]) => {
    const maxFileSize = normalizeAttachmentMaxBytes(me?.attachment_max_bytes);
    const selected = Array.from(files).slice(0, MAX_TOTAL_ATTACHMENTS);
    if (selected.length === 0) return;
    if (Array.from(files).length > 1) {
      toast(t("chat.attachment.oneAtATime"), "info");
    }
    const next: PendingAttachment[] = [];
    beginAttachmentUpload();
    try {
      for (const file of selected) {
        if (file.size > maxFileSize) {
          toast(t("chat.attachment.sizeExceeded", { file: file.name, size: formatBytes(maxFileSize) }), "error");
          continue;
        }
        const uploadTimeoutMs = attachmentUploadTimeoutMs(file.size);
        try {
          await yieldToMainThread();
          const bytes = new Uint8Array(await file.arrayBuffer());
          const mimeType =
            file.type || guessMimeTypeByName(file.name) || "application/octet-stream";
          const created = await apiCreateAttachment(
            {
              session_id: currentIdRef.current,
              name: file.name,
              size_bytes: file.size,
              kind: "other",
              mime_type: mimeType,
              file_data_base64: bytesToBase64(bytes),
              processable: false,
              truncated: false,
            },
            { timeoutMs: uploadTimeoutMs },
          );
          next.push({
            id: uid("f"),
            attachmentId: created.id,
            name: created.name,
            size: file.size,
            kind: created.kind,
            mimeType: created.mimeType,
            text: created.text,
            contentSha256: await sha256HexBytes(bytes),
            processable: created.processable,
            unsupportedReason: created.unsupportedReason,
            truncated: !!created.truncated,
          });
        } catch (err) {
          const message =
            err instanceof ApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : t("chat.attachment.readFailedRetry", { file: file.name });
          toast(message, "error");
        }
      }
      if (next.length > 0) {
        if (pendingAttachmentsRef.current.length > 0) {
          toast(t("chat.attachment.replaced"), "info");
        }
        setPendingAttachments(next);
      }
    } finally {
      endAttachmentUpload();
    }
  };

  const addPendingFiles = async (files: FileList | File[]) => {
    if (attachmentUploadBusyRef.current) {
      toast(t("chat.composer.attachmentProcessing"), "info");
      return;
    }
    await processPendingFiles(files);
  };

  const runtime = useExternalStoreRuntime({
    isRunning,
    messages,
    convertMessage,
    isSendDisabled: false,
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
        hasMoreSessions,
        loadingMoreSessions,
        loadMoreSessions,
        currentId,
        query,
        setQuery,
        isRunning,
        lastErrored,
        canRegenerate: !isRunning && messages.some((m) => m.role === "user"),
        messageAttachments,
        pendingAttachments,
        isAddingAttachment,
        addPendingFiles,
        removePendingAttachment,
        clearPendingAttachments,
        messageQueue,
        enqueueFromComposer,
        removeQueuedMessage,
        flushQueueHead,
        send: (text: string) => {
          void send(text);
        },
        regenerate,
        newSession,
        selectSession,
        deleteSession,
        sessionTodoPlan,
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
    processable: file.processable,
    unsupportedReason: file.unsupportedReason,
    truncated: file.truncated,
  }));
}

function attachmentUploadTimeoutMs(sizeBytes: number): number {
  const extra = Math.ceil(sizeBytes / (100 * 1024)) * 1000;
  return Math.min(ATTACHMENT_UPLOAD_TIMEOUT_MAX_MS, ATTACHMENT_UPLOAD_TIMEOUT_BASE_MS + extra);
}

function yieldToMainThread(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve());
  });
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

function guessMimeTypeByName(name: string): string | undefined {
  const lower = name.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".bmp")) return "image/bmp";
  return undefined;
}
