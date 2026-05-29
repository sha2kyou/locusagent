import type { ReactNode } from "react";
import { Loader2, Settings2 } from "lucide-react";
import { useAuth } from "@/app/auth";
import { useShell } from "@/app/AppShell";
import { Button } from "@/components/ui/button";

/** 工作区数据页的就绪门：未配置模型/容器未就绪时显示提示而非空列表 */
export function ReadyGate({ children }: { children: ReactNode }) {
  const { me, loading, readiness } = useAuth();
  const { openSettings } = useShell();

  if (loading || !me) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }

  if (readiness.reason === "needs_llm" || readiness.reason === "failed") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-surface/40 py-14 text-center">
        <p className="text-sm text-muted-foreground">
          {readiness.reason === "needs_llm" ? "尚未配置对话模型，工作区暂不可用。" : "Agent 部署失败，请检查配置。"}
        </p>
        <Button variant="primary" onClick={openSettings}>
          <Settings2 className="size-4" /> 打开设置
        </Button>
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
