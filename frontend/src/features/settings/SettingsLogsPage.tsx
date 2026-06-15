import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { getActivityLogs } from "@/api/endpoints";
import type { ActivityLogEntry } from "@/api/types";
import { cn } from "@/lib/utils";
import { formatFull, formatRelative } from "@/lib/format-time";

const POLL_MS = 5000;
const PAGE_LIMIT = 200;

const CATEGORY_LABELS: Record<string, string> = {
  mcp: "MCP",
  skill: "技能",
  memory: "记忆",
  env: "环境变量",
  chat: "对话",
  settings: "设置",
  workspace: "工作区",
  scheduled: "定时任务",
  tool: "工具",
  system: "系统",
};

function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

function levelClass(level: string): string {
  if (level === "error") return "text-destructive";
  if (level === "warn") return "text-amber-600 dark:text-amber-400";
  return "text-muted-foreground";
}

function DetailBlock({ detail }: { detail: Record<string, unknown> }) {
  const text = JSON.stringify(detail, null, 2);
  return (
    <pre className="mt-2 max-h-40 overflow-auto rounded-md border border-border/60 bg-muted/30 p-2 text-xs text-muted-foreground">
      {text}
    </pre>
  );
}

function LogRow({ entry }: { entry: ActivityLogEntry }) {
  const [open, setOpen] = useState(false);
  const hasDetail = entry.detail != null && Object.keys(entry.detail).length > 0;

  return (
    <div className="border-b border-border/60 px-3 py-2.5 last:border-0">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <time
          className="shrink-0 text-xs tabular-nums text-muted-foreground"
          title={formatFull(entry.ts)}
        >
          {formatRelative(entry.ts)}
        </time>
        <span className="inline-flex shrink-0 rounded-md bg-muted/60 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          {categoryLabel(entry.category)}
        </span>
        <span className={cn("min-w-0 flex-1 text-sm", levelClass(entry.level))}>{entry.message}</span>
        {hasDetail && (
          <button
            type="button"
            className="inline-flex shrink-0 items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
            详情
          </button>
        )}
      </div>
      {open && hasDetail && entry.detail && <DetailBlock detail={entry.detail} />}
    </div>
  );
}

export function SettingsLogsPage() {
  const [items, setItems] = useState<ActivityLogEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const topIdRef = useRef(0);

  const load = async (opts?: { silent?: boolean }) => {
    try {
      const { items: rows } = await getActivityLogs({ limit: PAGE_LIMIT });
      if (rows.length > 0) {
        topIdRef.current = Math.max(topIdRef.current, rows[0].id);
      }
      setItems(rows);
      setError(null);
    } catch (e) {
      if (!opts?.silent) setError((e as Error).message);
      if (!opts?.silent) setItems([]);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load({ silent: true }), POLL_MS);
    return () => clearInterval(timer);
  }, []);

  const categories = useMemo(() => {
    const set = new Set((items ?? []).map((i) => i.category));
    return Array.from(set).sort();
  }, [items]);

  const filtered = useMemo(() => {
    const list = items ?? [];
    if (categoryFilter === "all") return list;
    return list.filter((i) => i.category === categoryFilter);
  }, [items, categoryFilter]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">分类</span>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            className={cn(
              "rounded-md px-2 py-0.5 text-xs transition-colors",
              categoryFilter === "all"
                ? "bg-primary text-primary-foreground"
                : "bg-muted/60 text-muted-foreground hover:text-foreground",
            )}
            onClick={() => setCategoryFilter("all")}
          >
            全部
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              className={cn(
                "rounded-md px-2 py-0.5 text-xs transition-colors",
                categoryFilter === cat
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/60 text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setCategoryFilter(cat)}
            >
              {categoryLabel(cat)}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface/40">
        {loading && (
          <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            加载中…
          </div>
        )}

        {!loading && error && <p className="p-4 text-sm text-destructive">{error}</p>}

        {!loading && !error && filtered.length === 0 && (
          <p className="p-4 text-sm text-muted-foreground">暂无操作日志。</p>
        )}

        {!loading && !error && filtered.length > 0 && (
          <div className="max-h-[min(70vh,42rem)] overflow-y-auto">
            {filtered.map((entry) => (
              <LogRow key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </div>

      {!loading && !error && (items?.length ?? 0) >= PAGE_LIMIT && (
        <p className="text-xs text-muted-foreground">仅显示最近 {PAGE_LIMIT} 条，更早记录已归档。</p>
      )}
    </div>
  );
}
