import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
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
  type ChatMessage,
  type ChatPart,
  emptyAssistant,
  uid,
  userMessage,
} from "./model";
import { convertMessage } from "./convert";
import { coalesceHistory } from "./history";

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

export function ChatProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const { readiness } = useAuth();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [lastErrored, setLastErrored] = useState(false);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const currentIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pollTokenRef = useRef(0);

  const setCurrent = (id: string | null) => {
    currentIdRef.current = id;
    setCurrentId(id);
  };

  // ---- 会话列表 ----
  const refreshSessions = async () => {
    try {
      const { items } = await listSessions();
      items.sort((a, b) => (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at));
      setSessions(items);
    } catch {
      /* 容器未就绪等：忽略，由就绪提示兜底 */
    } finally {
      setLoadingSessions(false);
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

  // ---- 标题自动生成轮询 ----
  const watchTitle = (sid: string) => {
    let tries = 0;
    const timer = window.setInterval(async () => {
      tries += 1;
      await refreshSessions();
      const found = (await listSessions().catch(() => ({ items: [] as SessionMeta[] }))).items.find((s) => s.id === sid);
      if (tries >= 12 || (found && found.title && found.title !== DEFAULT_TITLE)) {
        clearInterval(timer);
      }
    }, 2500);
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

  // ---- 发送 / 重跑 ----
  // appendUser=false 用于"重新生成 / 重试"：复用最后一条用户消息重跑，
  // 后端在 new_user == 库内最后一条 user 时不会重复落库（见 v1._prepare_messages）。
  const runTurn = async (text: string, opts: { appendUser: boolean }) => {
    abortChat();
    setLastErrored(false);
    setMessages((prev) => {
      if (opts.appendUser) return [...prev, userMessage(text), emptyAssistant()];
      const arr = [...prev];
      while (arr.length && arr[arr.length - 1].role === "assistant") arr.pop();
      return [...arr, emptyAssistant()];
    });
    setIsRunning(true);

    const ac = new AbortController();
    abortRef.current = ac;

    const sid = currentIdRef.current;
    const body = {
      messages: [{ role: "user", content: text }],
      stream: true as const,
      ...(sid ? { session_id: sid } : {}),
    };

    let firstToken = true;
    try {
      await streamChatCompletion(
        body,
        {
          onMessage: (chunk) => {
            if (chunk.session_id && !currentIdRef.current) {
              setCurrent(chunk.session_id);
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
        toast("该会话仍在生成中", "info");
        if (currentIdRef.current) startActiveRunPoll(currentIdRef.current);
        return;
      } else {
        updateLastAssistant((p) => p, err.message || "请求失败");
        setLastErrored(true);
      }
    } finally {
      if (abortRef.current === ac) abortRef.current = null;
      setIsRunning(false);
      void refreshSessions();
    }
  };

  const send = (text: string) => runTurn(text, { appendUser: true });

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
    abortChat();
    stopActiveRunPoll();
    setCurrent(null);
    setMessages([]);
    setIsRunning(false);
  };

  const selectSession = (id: string) => {
    abortChat();
    stopActiveRunPoll();
    setCurrent(id);
    setIsRunning(false);
    void (async () => {
      try {
        const { items } = await getSessionMessages(id);
        if (currentIdRef.current !== id) return;
        setMessages(coalesceHistory(items));
        const { run } = await getActiveRun(id);
        if (currentIdRef.current === id && run?.status === "running") {
          setIsRunning(true);
          startActiveRunPoll(id);
        }
      } catch (e) {
        toast((e as Error).message, "error");
      }
    })();
  };

  const deleteSession = async (id: string) => {
    await apiDeleteSession(id);
    await refreshSessions();
    if (currentIdRef.current === id) newSession();
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
      if (text) await send(text);
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
      const t = msgs[i].parts.map((p) => (p.type === "text" ? p.text : "")).join("").trim();
      return t || null;
    }
  }
  return null;
}
