import { useEffect, useState } from "react";
import { Loader2, Wrench } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ListCard } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { ReadyGate } from "@/components/ReadyGate";
import {
  listToolToggles,
  updateBuiltinToolToggle,
  updateMcpToggle,
  updateSkillToggle,
} from "@/api/endpoints";
import type { ToolToggleItem, ToolToggleOverview } from "@/api/types";
import { Empty, Loading } from "@/features/skills/SkillsRoute";

export function ToolsRoute() {
  const toast = useToast();
  const [data, setData] = useState<ToolToggleOverview | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const load = async () => {
    try {
      const next = await listToolToggles();
      setData(next);
    } catch (e) {
      toast((e as Error).message, "error");
      setData({ builtin_tools: [], skills: [], mcp_servers: [] });
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = async (
    kind: "builtin" | "skills" | "mcp",
    item: ToolToggleItem,
  ) => {
    const key = `${kind}:${item.name}`;
    setBusyKey(key);
    try {
      const nextEnabled = !item.enabled;
      if (kind === "builtin") {
        await updateBuiltinToolToggle(item.name, nextEnabled);
      } else if (kind === "skills") {
        await updateSkillToggle(item.name, nextEnabled);
      } else {
        await updateMcpToggle(item.name, nextEnabled);
      }
      await load();
      toast(`${item.name} 已${nextEnabled ? "启用" : "禁用"}`, "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <PageContainer
      title="工具"
      subtitle="可按需启用或禁用内置工具、技能和 MCP 服务"
      actions={
        data ? (
          <Badge variant="outline">
            内置 {data.builtin_tools.length} / 技能 {data.skills.length} / MCP {data.mcp_servers.length}
          </Badge>
        ) : undefined
      }
    >
      <ReadyGate>
        {data === null ? (
          <Loading />
        ) : (
          <div className="space-y-6">
            <ToggleGroup
              title="内置工具"
              items={data.builtin_tools}
              busyKey={busyKey}
              kind="builtin"
              onToggle={toggle}
            />
            <ToggleGroup
              title="Skills"
              items={data.skills}
              busyKey={busyKey}
              kind="skills"
              onToggle={toggle}
            />
            <ToggleGroup
              title="MCP"
              items={data.mcp_servers}
              busyKey={busyKey}
              kind="mcp"
              onToggle={toggle}
            />
          </div>
        )}
      </ReadyGate>
    </PageContainer>
  );
}

function ToggleGroup({
  title,
  items,
  busyKey,
  kind,
  onToggle,
}: {
  title: string;
  items: ToolToggleItem[];
  busyKey: string | null;
  kind: "builtin" | "skills" | "mcp";
  onToggle: (kind: "builtin" | "skills" | "mcp", item: ToolToggleItem) => Promise<void>;
}) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
      {items.length === 0 ? (
        <Empty text="暂无条目" />
      ) : (
        items.map((item) => {
          const key = `${kind}:${item.name}`;
          const busy = busyKey === key;
          return (
            <ListCard key={key}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Wrench className="size-4 text-muted-foreground" />
                    <span className="font-medium">{item.name}</span>
                    <Badge variant={item.enabled ? "success" : "outline"}>
                      {item.enabled ? "已启用" : "已禁用"}
                    </Badge>
                    {kind === "skills" && item.source ? (
                      <Badge variant="brand">{item.source === "public" ? "公共" : "私有"}</Badge>
                    ) : null}
                    {kind === "mcp" && item.transport ? <Badge>{item.transport}</Badge> : null}
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
                    void onToggle(kind, item);
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
    </section>
  );
}
