import { useEffect, useState } from "react";
import { Loader2, Wrench } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ListCard } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { ReadyGate } from "@/components/ReadyGate";
import { listToolToggles, updateBuiltinToolToggle } from "@/api/endpoints";
import type { ToolToggleItem, ToolToggleOverview } from "@/api/types";
import { Empty, Loading } from "@/features/skills/SkillsRoute";

export function ToolsRoute() {
  const toast = useToast();
  const [data, setData] = useState<ToolToggleOverview | null>(null);
  const [busyName, setBusyName] = useState<string | null>(null);

  const load = async () => {
    try {
      const next = await listToolToggles();
      setData(next);
    } catch (e) {
      toast((e as Error).message, "error");
      setData({ builtin_tools: [] });
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = async (item: ToolToggleItem) => {
    setBusyName(item.name);
    try {
      const nextEnabled = !item.enabled;
      await updateBuiltinToolToggle(item.name, nextEnabled);
      await load();
      toast(`${item.name} 已${nextEnabled ? "启用" : "禁用"}`, "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusyName(null);
    }
  };

  return (
    <PageContainer
      title="工具"
      subtitle="可按需启用或禁用工具"
      actions={
        data ? <Badge variant="outline">工具 {data.builtin_tools.length}</Badge> : undefined
      }
    >
      <ReadyGate>
        {data === null ? (
          <Loading />
        ) : (
          <div className="space-y-6">
            {data.builtin_tools.length === 0 ? (
              <Empty text="暂无条目" />
            ) : (
              data.builtin_tools.map((item) => {
                const busy = busyName === item.name;
                return (
                  <ListCard key={item.name}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Wrench className="size-4 text-muted-foreground" />
                          <span className="font-medium">{item.name}</span>
                          <Badge variant={item.enabled ? "success" : "outline"}>
                            {item.enabled ? "已启用" : "已禁用"}
                          </Badge>
                        </div>
                        {item.description ? (
                          <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
                        ) : null}
                      </div>
                      <Button
                        variant={item.enabled ? "secondary" : "primary"}
                        size="sm"
                        disabled={busy}
                        onClick={() => {
                          void toggle(item);
                        }}
                      >
                        {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                        {item.enabled ? "禁用" : "启用"}
                      </Button>
                    </div>
                  </ListCard>
                );
              })
            )}
          </div>
        )}
      </ReadyGate>
    </PageContainer>
  );
}
