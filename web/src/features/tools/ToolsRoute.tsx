import { useEffect, useState } from "react";
import { Loader2, Wrench } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Badge } from "@/components/ui/badge";
import { CollapsibleSection, ListCard } from "@/components/ui/panel";
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

  const setToolEnabled = async (item: ToolToggleItem, enabled: boolean) => {
    if (item.enabled === enabled) return;
    setBusyName(item.name);
    try {
      await updateBuiltinToolToggle(item.name, enabled);
      await load();
      toast(`${item.name} 已${enabled ? "启用" : "禁用"}`, "success");
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
                  <ListCard key={item.name} className="p-0 overflow-hidden">
                    <div className="flex items-start justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Wrench className="size-4 text-muted-foreground" />
                          <span className="font-medium">{item.name}</span>
                          <Badge variant={item.enabled ? "success" : "outline"}>
                            {item.enabled ? "已启用" : "已禁用"}
                          </Badge>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={item.enabled}
                          aria-label={`${item.name}${item.enabled ? "已启用，点击禁用" : "已禁用，点击启用"}`}
                          disabled={busy}
                          onClick={() => {
                            void setToolEnabled(item, !item.enabled);
                          }}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full border transition-colors focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 ${
                            item.enabled
                              ? "border-brand bg-brand/90"
                              : "border-border-strong bg-secondary"
                          }`}
                        >
                          <span
                            className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                              item.enabled ? "translate-x-6" : "translate-x-1"
                            }`}
                          />
                        </button>
                        {busy ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
                      </div>
                    </div>
                    {item.description ? (
                      <CollapsibleSection summary="说明">
                        <p className="text-sm text-foreground">{item.description}</p>
                      </CollapsibleSection>
                    ) : null}
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
