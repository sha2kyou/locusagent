import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/app/auth";

/** 工作区数据页：session 加载完成前显示占位。 */
export function ReadyGate({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading || !me) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }

  return <>{children}</>;
}
