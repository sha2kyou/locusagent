import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, setWorkspaceId } from "@/api/client";
import { getMe } from "@/api/endpoints";
import type { Me } from "@/api/types";
import {
  AUTH_LOAD_FAILED,
  READINESS_LABEL_ABSENT,
  READINESS_LABEL_CREATING,
  READINESS_LABEL_FAILED,
  READINESS_LABEL_PAUSED,
  READINESS_LABEL_READY,
  READINESS_LABEL_STOPPED,
} from "@/lib/agent-status-copy";
import { Button } from "@/components/ui/button";

export interface AgentReadiness {
  ready: boolean;
  label: string;
  tone: "ready" | "pending" | "blocked";
  /** 阻塞原因：创建中 / 失败 等，用于提示与禁用输入 */
  reason?: "creating" | "paused" | "stopped" | "failed" | "absent";
}

export function readinessOf(me: Me | null): AgentReadiness {
  if (!me) return { ready: false, label: "加载中", tone: "pending" };
  if (me.provision_status === "failed")
    return { ready: false, label: READINESS_LABEL_FAILED, tone: "blocked", reason: "failed" };
  switch (me.container_status) {
    case "running":
      return { ready: true, label: READINESS_LABEL_READY, tone: "ready" };
    case "creating":
      return { ready: false, label: READINESS_LABEL_CREATING, tone: "pending", reason: "creating" };
    case "paused":
      return { ready: true, label: READINESS_LABEL_PAUSED, tone: "pending", reason: "paused" };
    case "stopped":
      return { ready: true, label: READINESS_LABEL_STOPPED, tone: "pending", reason: "stopped" };
    default:
      return { ready: false, label: READINESS_LABEL_ABSENT, tone: "pending", reason: "absent" };
  }
}

interface AuthState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<Me | null>;
  readiness: AgentReadiness;
  /** 容器从非 running 恢复为 running 时递增，供各页重新拉取数据 */
  agentRecoveryEpoch: number;
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
  const [error, setError] = useState<string | null>(null);
  const [agentRecoveryEpoch, setAgentRecoveryEpoch] = useState(0);
  const pollRef = useRef<number | null>(null);
  const prevContainerRef = useRef<string | undefined>(undefined);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const next = await getMe(true);
      if (next.current_workspace_id) setWorkspaceId(next.current_workspace_id);
      setMe(next);
      return next;
    } catch (e) {
      setMe(null);
      if (e instanceof ApiError && e.status === 401) {
        setError(null);
      } else {
        setError(e instanceof ApiError ? e.message : AUTH_LOAD_FAILED);
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    const cur = me?.container_status;
    const prev = prevContainerRef.current;
    prevContainerRef.current = cur;
    if (prev && prev !== "running" && cur === "running") {
      setAgentRecoveryEpoch((n) => n + 1);
    }
  }, [me?.container_status]);

  useEffect(() => {
    if (!loading && !me && !error) {
      window.location.href = "/login";
    }
  }, [loading, me, error]);

  // 部署/恢复进行中轮询，直到 running（含休眠唤醒、停止后重启）
  useEffect(() => {
    const needsPoll =
      me?.container_status === "creating" ||
      me?.container_status === "paused" ||
      me?.container_status === "stopped" ||
      (me?.provision_status === "pending" && me?.container_status !== "running");
    if (!needsPoll) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    void reload();
    pollRef.current = window.setInterval(() => void reload(), 3000);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [me?.container_status, me?.provision_status, reload]);

  let body: ReactNode = children;
  if (loading) {
    body = null;
  } else if (error) {
    body = (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center text-sm">
        <p className="text-muted-foreground">{error}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setLoading(true);
            void reload();
          }}
        >
          重试
        </Button>
      </div>
    );
  } else if (!me) {
    body = null;
  }

  return (
    <AuthContext.Provider
      value={{ me, loading, error, reload, readiness: readinessOf(me), agentRecoveryEpoch }}
    >
      {body}
    </AuthContext.Provider>
  );
}
