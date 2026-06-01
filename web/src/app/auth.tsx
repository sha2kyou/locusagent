import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getMe } from "@/api/endpoints";
import { setWorkspaceId } from "@/api/client";
import type { Me } from "@/api/types";

export interface AgentReadiness {
  ready: boolean;
  label: string;
  tone: "ready" | "pending" | "blocked";
  /** 阻塞原因：需要配置 LLM / 创建中 / 失败 等，用于提示与禁用输入 */
  reason?: "needs_llm" | "creating" | "paused" | "stopped" | "failed" | "absent";
}

export function readinessOf(me: Me | null): AgentReadiness {
  if (!me) return { ready: false, label: "加载中", tone: "pending" };
  if (!me.llm_configured)
    return { ready: false, label: "未配置模型", tone: "blocked", reason: "needs_llm" };
  if (me.provision_status === "failed")
    return { ready: false, label: "部署失败", tone: "blocked", reason: "failed" };
  switch (me.container_status) {
    case "running":
      return { ready: true, label: "已就绪", tone: "ready" };
    case "creating":
      return { ready: false, label: "启动中", tone: "pending", reason: "creating" };
    case "paused":
      return { ready: true, label: "已休眠", tone: "pending", reason: "paused" };
    case "stopped":
      return { ready: true, label: "已停止", tone: "pending", reason: "stopped" };
    default:
      return { ready: false, label: "未就绪", tone: "pending", reason: "absent" };
  }
}

interface AuthState {
  me: Me | null;
  loading: boolean;
  reload: () => Promise<Me | null>;
  readiness: AgentReadiness;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<number | null>(null);

  const reload = useCallback(async () => {
    try {
      const next = await getMe();
      if (next.current_workspace_id) setWorkspaceId(next.current_workspace_id);
      setMe(next);
      return next;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 容器 creating / (absent + provision pending) 时轮询，直到 running
  useEffect(() => {
    const needsPoll =
      me?.container_status === "creating" ||
      (me?.container_status === "absent" && me?.provision_status === "pending");
    if (!needsPoll) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = window.setInterval(() => void reload(), 3000);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [me?.container_status, me?.provision_status, reload]);

  return (
    <AuthContext.Provider value={{ me, loading, reload, readiness: readinessOf(me) }}>
      {children}
    </AuthContext.Provider>
  );
}
