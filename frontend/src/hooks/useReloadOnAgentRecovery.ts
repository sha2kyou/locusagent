import { useEffect, useRef } from "react";
import { useAuth } from "@/app/auth";

/** 挂载时加载一次；Agent 容器恢复为 running 时（epoch 递增）再加载。 */
export function useReloadOnAgentRecovery(reload: () => void | Promise<void>) {
  const { agentRecoveryEpoch } = useAuth();
  const reloadRef = useRef(reload);
  reloadRef.current = reload;

  useEffect(() => {
    void reloadRef.current();
  }, [agentRecoveryEpoch]);
}
