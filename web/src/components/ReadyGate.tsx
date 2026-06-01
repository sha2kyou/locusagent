import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/app/auth";
import { PROVISION_FAILED_HINT, ProvisionRetryButton } from "@/components/ProvisionRetry";

/** 工作区数据页的就绪门：容器未就绪时显示提示而非空列表 */
export function ReadyGate({ children }: { children: ReactNode }) {
  const { me, loading, readiness } = useAuth();
  if (loading || !me) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }

  if (readiness.reason === "failed") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-surface/40 py-14 text-center">
        <p className="text-sm text-muted-foreground">{PROVISION_FAILED_HINT}</p>
        <ProvisionRetryButton size="md" />
      </div>
    );
  }

  if (readiness.reason === "creating" || readiness.reason === "absent") {
    return (
      <div className="flex flex-col items-center gap-2 py-14 text-center text-sm text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
        Agent 启动中，请稍候…
      </div>
    );
  }

  return <>{children}</>;
}
