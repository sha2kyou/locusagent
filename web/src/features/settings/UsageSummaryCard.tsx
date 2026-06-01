import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { getUsageSummary } from "@/api/endpoints";
import type { UsageSummary } from "@/api/types";
import { formatTokenCount, usageScenarioLabel } from "./usageLabels";

interface AggregatedRow {
  label: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  api_calls: number;
  event_count: number;
}

export function UsageSummaryCard({ active }: { active?: boolean }) {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getUsageSummary()
      .then((summary) => {
        if (!cancelled) setData(summary);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active]);

  const totals = data?.totals;
  const items = data?.items ?? [];
  const aggregated: AggregatedRow[] = (() => {
    const m = new Map<string, AggregatedRow>();
    for (const row of items) {
      const hasModel = !!(row.model && row.model.trim());
      const key = hasModel ? `model:${row.model}` : `service:${row.scenario}`;
      const label = hasModel ? String(row.model) : usageScenarioLabel(row.scenario);
      const cur =
        m.get(key) ??
        {
          label,
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
          api_calls: 0,
          event_count: 0,
        };
      cur.prompt_tokens += row.prompt_tokens;
      cur.completion_tokens += row.completion_tokens;
      cur.total_tokens += row.total_tokens;
      cur.api_calls += row.api_calls;
      cur.event_count += row.event_count;
      m.set(key, cur);
    }
    return Array.from(m.values()).sort((a, b) => b.total_tokens - a.total_tokens || b.api_calls - a.api_calls);
  })();

  return (
    <section className="rounded-lg border border-border bg-surface/40 p-4">
      <h3 className="mb-1 text-sm font-semibold">用量统计</h3>
      <p className="mb-3 text-xs text-muted-foreground">
        按模型/服务汇总：对话 Token、Tavily / 嵌入等第三方调用次数。
      </p>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          加载中…
        </div>
      )}

      {!loading && error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {!loading && !error && totals && (
        <div className="mb-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span>
            总 Token：<strong className="text-foreground">{formatTokenCount(totals.total_tokens)}</strong>
          </span>
          <span>
            第三方调用：<strong className="text-foreground">{totals.api_calls}</strong> 次
          </span>
          <span>
            记录条数：<strong className="text-foreground">{totals.event_count}</strong>
          </span>
        </div>
      )}

      {!loading && !error && aggregated.length === 0 && (
        <p className="text-sm text-muted-foreground">暂无用量数据，完成一次对话后将开始累计。</p>
      )}

      {!loading && !error && aggregated.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead className="border-b border-border bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">模型/服务</th>
                <th className="px-3 py-2 font-medium text-right">Token</th>
                <th className="px-3 py-2 font-medium text-right">API 次数</th>
              </tr>
            </thead>
            <tbody>
              {aggregated.map((row) => (
                <tr key={row.label} className="border-b border-border/60 last:border-0">
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{row.label}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.total_tokens > 0 ? formatTokenCount(row.total_tokens) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.api_calls > 0 ? row.api_calls : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
