import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { PageContainer } from "@/components/PageContainer";
import { Badge } from "@/components/ui/badge";
import { CollapsibleSection, ListCard } from "@/components/ui/panel";
import { Empty, listItemBriefClass, Loading } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { ReadyGate } from "@/components/ReadyGate";
import { listToolToggles } from "@/api/endpoints";
import type { ToolToggleOverview } from "@/api/types";

function getDescriptionMeta(description: string | undefined, noDescription: string): { brief: string; full: string } {
  if (!description?.trim()) return { brief: noDescription, full: noDescription };
  const compact = description.replace(/\s+/g, " ").trim();
  if (compact.length <= 56) return { brief: compact, full: description.trim() };
  return { brief: `${compact.slice(0, 56)}...`, full: description.trim() };
}

export function ToolsRoute() {
  const { t } = useTranslation();
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
    void load();
  }, []);

  return (
    <PageContainer
      title={t("tools.title")}
      subtitle={t("tools.subtitle")}
      actions={data ? <Badge variant="outline">{t("tools.count", { count: data.builtin_tools.length })}</Badge> : undefined}
    >
      <ReadyGate>
        {data === null ? (
          <Loading />
        ) : data.builtin_tools.length === 0 ? (
          <Empty text={t("tools.empty")} />
        ) : (
          <div className="space-y-2">
            {data.builtin_tools.map((item) => {
              const desc = getDescriptionMeta(item.description, t("tools.noDescription"));
              return (
                <ListCard key={item.name} className="p-0 overflow-hidden">
                  <div className="flex items-start gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{item.name}</span>
                      </div>
                      <p className={listItemBriefClass}>{desc.brief}</p>
                    </div>
                  </div>
                  <CollapsibleSection summary={t("common.actions.details")}>
                    <div className="space-y-2 text-sm">
                      <p className="whitespace-pre-wrap text-foreground">{desc.full}</p>
                    </div>
                  </CollapsibleSection>
                </ListCard>
              );
            })}
          </div>
        )}
      </ReadyGate>
    </PageContainer>
  );
}
