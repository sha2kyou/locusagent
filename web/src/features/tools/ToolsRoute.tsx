import { useEffect, useState } from "react";
import { PageContainer } from "@/components/PageContainer";
import { Badge } from "@/components/ui/badge";
import { CollapsibleSection, ListCard } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { ReadyGate } from "@/components/ReadyGate";
import { listToolToggles } from "@/api/endpoints";
import type { ToolToggleOverview } from "@/api/types";
import { Empty, Loading } from "@/features/skills/SkillsRoute";

function getDescriptionMeta(description?: string): { brief: string; isTruncated: boolean; full: string } {
  if (!description?.trim()) return { brief: "暂无说明", isTruncated: false, full: "暂无说明" };
  const compact = description.replace(/\s+/g, " ").trim();
  if (compact.length <= 56) return { brief: compact, isTruncated: false, full: description.trim() };
  return { brief: `${compact.slice(0, 56)}...`, isTruncated: true, full: description.trim() };
}

export function ToolsRoute() {
  const toast = useToast();
  const [data, setData] = useState<ToolToggleOverview | null>(null);

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
                const desc = getDescriptionMeta(item.description);
                return (
                  <ListCard key={item.name} className="p-0 overflow-hidden">
                    <div className="flex items-start gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{item.name}</span>
                        </div>
                        <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                          {desc.brief}
                        </p>
                      </div>
                    </div>
                    {desc.isTruncated ? (
                      <CollapsibleSection summary="详情">
                        <div className="space-y-2 text-sm">
                          <p className="whitespace-pre-wrap text-foreground">{desc.full}</p>
                        </div>
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
