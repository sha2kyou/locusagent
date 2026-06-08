import { useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { ensureContainer } from "@/api/endpoints";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export {
  PROVISION_FAILED_HINT,
  PROVISION_FAILED_STATUS,
} from "@/lib/agent-status-copy";

export function useProvisionRetry() {
  const { reload } = useAuth();
  const toast = useToast();
  const [retrying, setRetrying] = useState(false);

  const retry = async () => {
    setRetrying(true);
    try {
      toast("已提交重试，正在重新部署 AgentPod…", "info");
      await ensureContainer();
      await reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setRetrying(false);
    }
  };

  return { retry, retrying };
}

export function ProvisionRetryButton({ size = "sm" }: { size?: "sm" | "md" }) {
  const { retry, retrying } = useProvisionRetry();
  return (
    <Button
      variant={size === "sm" ? "secondary" : "primary"}
      size={size}
      className={size === "sm" ? "h-7 shrink-0 text-xs" : undefined}
      disabled={retrying}
      onClick={() => void retry()}
    >
      {retrying ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
      {size === "sm" ? "重试" : "重试部署"}
    </Button>
  );
}
