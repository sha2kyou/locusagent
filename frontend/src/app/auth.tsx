import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { ApiError, setWorkspaceId } from "@/api/client";
import { getMe } from "@/api/endpoints";
import type { Me } from "@/api/types";
import { AUTH_LOAD_FAILED } from "@/lib/agent-status-copy";
import { Button } from "@/components/ui/button";

interface AuthState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<Me | null>;
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

  const reload = useCallback(async () => {
    setError(null);
    try {
      const next = await getMe(true);
      if (next.current_workspace_id) setWorkspaceId(next.current_workspace_id);
      setMe(next);
      return next;
    } catch (e) {
      setMe(null);
      setError(e instanceof ApiError ? e.message : AUTH_LOAD_FAILED);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

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
    <AuthContext.Provider value={{ me, loading, error, reload }}>
      {body}
    </AuthContext.Provider>
  );
}
