import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import {
  cancelRun,
  deleteSession as apiDeleteSession,
  getActiveRun,
  getSessionMessages,
  listSessions,
} from "@/api/endpoints";
import type { SessionMeta } from "@/api/types";
import { streamChatCompletion } from "@/api/stream";
import { useToast } from "@/components/ui/toast";
import { useAuth, type AgentReadiness } from "@/app/auth";
import {
  appendText,
  type ChatAttachment,
  type ChatMessage,
  type ChatPart,
  emptyAssistant,
  uid,
  userMessage,
} from "./model";
import { convertMessage } from "./convert";
import { coalesceHistory } from "./history";

export interface PendingAttachment {
  id: string;
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
  sessions: SessionMeta[];
  loadingSessions: boolean;
  currentId: string | null;
  query: string;
  setQuery: (q: string) => void;
  readiness: AgentReadiness;
  isRunning: boolean;
  lastErrored: boolean;
  canRegenerate: boolean;
  pendingAttachments: PendingAttachment[];
  addPendingFiles: (files: FileList | File[]) => Promise<void>;
  removePendingAttachment: (id: string) => void;
  clearPendingAttachments: () => void;
  send: (text: string) => void;
  regenerate: () => void;
  newSession: () => void;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => Promise<void>;
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

function chatPath(sessionId: string | null): string {
  return sessionId ? `/chat/${encodeURIComponent(sessionId)}` : "/chat";
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const { readiness, me } = useAuth();
  const navigate = useNavigate();
  const urlSessionId = useParams().sessionId ?? null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [lastErrored, setLastErrored] = useState(false);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);

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

  const setCurrent = (id: string | null) => {
    currentIdRef.current = id;
    setCurrentId(id);
  };

  // ---- 会话列表 ----
  const refreshSessions = async () => {
    try {
      const { items } = await listSessions();
      items.sort((a, b) => (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at));
      if (mountedRef.current) setSessions(items);
    } catch {
      /* 容器未就绪等：忽略，由就绪提示兜底 */
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
      await refreshSessions();
      const found = (await listSessions().catch(() => ({ items: [] as SessionMeta[] }))).items.find((s) => s.id === sid);
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
    let lastKey = "";
    const tick = async () => {
      if (token !== pollTokenRef.current) return;
      try {
        const { run } = await getActiveRun(sid);
        const { items } = await getSessionMessages(sid);
        const key = `${items.length}:${items[items.length - 1]?.id ?? ""}:${items[items.length - 1]?.content?.length ?? 0}`;
        if (key !== lastKey) {
          lastKey = key;
          setMessages(coalesceHistory(items));
        }
        if (run?.status === "running") {
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
        const { items } = await getSessionMessages(id);
        if (token !== loadTokenRef.current || !mountedRef.current || currentIdRef.current !== id) {
          return;
        }
        setMessages(coalesceHistory(items));
        const { run } = await getActiveRun(id);
        if (token !== loadTokenRef.current || !mountedRef.current || currentIdRef.current !== id) {
          return;
        }
        if (run?.status === "running") {
          setIsRunning(true);
          startActiveRunPoll(id);
        }
      } catch (e) {
        if (token !== loadTokenRef.current || !mountedRef.current) return;
        toast((e as Error).message || "对话不存在", "error");
        resetToNewChat();
        navigate("/chat", { replace: true });
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
    },
  ) => {
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
      messages: [{ role: "user", content: opts.requestContent ?? opts.requestText ?? text }],
      stream: true as const,
      ...(sid ? { session_id: sid } : {}),
    };

    let firstToken = true;
    try {
      await streamChatCompletion(
        body,
        {
          onMessage: (chunk) => {
            if (!mountedRef.current || ac.signal.aborted) return;
            if (chunk.session_id) {
              if (!currentIdRef.current) setCurrent(chunk.session_id);
              const path = chatPath(chunk.session_id);
              if (window.location.pathname !== path) {
                navigate(path, { replace: true });
              }
              void refreshSessions();
              watchTitle(chunk.session_id);
            }
            const ev = chunk.x_event;
            if (ev === "tool_call") {
              updateLastAssistant((parts) => [
                ...parts,
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
              const delta = chunk.choices?.[0]?.delta?.content;
              if (delta) {
                firstToken = false;
                updateLastAssistant((parts) => appendText(parts, delta));
              }
            }
          },
          onRetry: (attempt, sec) => {
            toast(`Agent 启动中，${sec}s 后重试（${attempt}）`, "info");
          },
        },
        { signal: ac.signal },
      );
    } catch (e) {
      const err = e as { code?: string; message?: string };
      if (ac.signal.aborted) {
        if (firstToken) updateLastAssistant((p) => appendText(p, "（已停止生成）"));
      } else if (err.code === "run_in_progress") {
        toast("该对话仍在生成中", "info");
        if (mountedRef.current && currentIdRef.current) startActiveRunPoll(currentIdRef.current);
        return;
      } else {
        updateLastAssistant((p) => p, err.message || "请求失败");
        setLastErrored(true);
      }
    } finally {
      if (abortRef.current === ac) abortRef.current = null;
      if (!mountedRef.current) return;
      setIsRunning(false);
      void refreshSessions();
    }
  };

  const send = (
    text: string,
    requestText?: string,
    requestContent?: ChatRequestContent,
    displayAttachments?: ChatAttachment[],
  ) => runTurn(text, { appendUser: true, requestText, requestContent, displayAttachments });

  const regenerate = () => {
    if (isRunning) return;
    const text = lastUserText(messages);
    if (!text) return;
    void runTurn(text, { appendUser: false });
  };

  const cancel = async () => {
    abortChat();
    stopRunningTools("已停止");
    setIsRunning(false);
    const sid = currentIdRef.current;
    if (sid) await cancelRun(sid).catch(() => {});
  };

  // ---- 会话操作 ----
  const newSession = () => {
    navigate("/chat");
  };

  const selectSession = (id: string) => {
    navigate(chatPath(id));
  };

  const deleteSession = async (id: string) => {
    const wasCurrent = currentIdRef.current === id || urlSessionId === id;
    if (wasCurrent) {
      abortChat();
      stopActiveRunPoll();
    }
    await apiDeleteSession(id);
    if (!mountedRef.current) return;
    await refreshSessions();
    if (wasCurrent && mountedRef.current) navigate("/chat");
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
          next.push({
            id: uid("f"),
            name: file.name,
            size: file.size,
            kind: "text",
            text: truncated ? `${normalized.slice(0, MAX_ATTACHMENT_CHARS)}\n...（文件过长，已截断）` : normalized,
            processable: true,
            truncated,
          });
        } else if (isImageFile(file)) {
          const imageDataUrl = await fileToDataUrl(file);
          next.push({
            id: uid("f"),
            name: file.name,
            size: file.size,
            kind: "image",
            mimeType: file.type || guessMimeTypeByName(file.name) || "image/png",
            imageDataUrl,
            processable: true,
            truncated: false,
          });
        } else {
          next.push({
            id: uid("f"),
            name: file.name,
            size: file.size,
            kind: "other",
            processable: false,
            unsupportedReason: "当前仅支持文本或图片附件",
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
      const requestText = buildRequestText(text, attachments);
      const requestContent = buildRequestContent(text, attachments);
      const displayAttachments = buildDisplayAttachments(attachments);
      clearPendingAttachments();
      await send(displayText, requestText, requestContent, displayAttachments);
    },
    onCancel: cancel,
  });

  return (
    <ChatContext.Provider
      value={{
        sessions,
        loadingSessions,
        currentId,
        query,
        setQuery,
        readiness,
        isRunning,
        lastErrored,
        canRegenerate: !isRunning && messages.some((m) => m.role === "user"),
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

function lastUserText(msgs: ChatMessage[]): string | null {
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "user") {
      const t = (
        msgs[i].sourceText ??
        msgs[i].parts.map((p) => (p.type === "text" ? p.text : "")).join("")
      ).trim();
      return t || null;
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
    id: file.id,
    name: file.name,
    kind: file.kind,
    mimeType: file.mimeType,
    text: file.kind === "text" ? file.text : undefined,
    processable: file.processable,
    unsupportedReason: file.unsupportedReason,
    truncated: file.truncated,
  }));
}

function buildRequestText(text: string, attachments: PendingAttachment[]): string {
  const clean = text.trim();
  if (attachments.length === 0) return clean;
  const file = attachments[0];
  if (!file.processable) {
    return [
      clean,
      `用户上传了 1 个附件：name=${file.name}, size=${formatBytes(file.size)}。`,
      `该附件当前无法解析内容（${file.unsupportedReason ?? "未知原因"}）。`,
      "请直接告知用户：当前无法处理该格式附件；请改为上传文本文件，或把内容粘贴到对话中。",
      "不要猜测或编造附件内容。",
    ]
      .filter(Boolean)
      .join("\n\n");
  }
  if (file.kind === "image") {
    return [
      clean,
      `用户上传了 1 张图片：name=${file.name}, size=${formatBytes(file.size)}。`,
      "图片内容会随同本次请求发送，请结合图片与文字上下文回答。",
    ]
      .filter(Boolean)
      .join("\n\n");
  }
  const meta = [
    `name=${file.name}`,
    `size=${formatBytes(file.size)}`,
    file.truncated ? "truncated=true" : "truncated=false",
  ].join(", ");
  return [clean, "以下是用户上传的附件内容：", `[附件 1] (${meta})\n${file.text ?? ""}`]
    .filter(Boolean)
    .join("\n\n");
}

function buildRequestContent(text: string, attachments: PendingAttachment[]): ChatRequestContent {
  const clean = text.trim();
  if (attachments.length === 0) return clean;
  const file = attachments[0];
  if (!file.processable) return buildRequestText(clean, attachments);
  if (file.kind !== "image") return buildRequestText(clean, attachments);
  if (!file.imageDataUrl) return buildRequestText(clean, attachments);

  const parts: ({ type: "text"; text: string } | { type: "image_url"; image_url: { url: string } })[] = [];
  if (clean) {
    parts.push({ type: "text", text: clean });
  } else {
    parts.push({ type: "text", text: "请基于这张图片进行分析。" });
  }
  parts.push({ type: "image_url", image_url: { url: file.imageDataUrl } });
  return parts;
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
