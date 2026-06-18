import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { getEmbeddingProgress } from "@/api/endpoints";
import type { EmbeddingProgress, EmbeddingStateCounts } from "@/api/types";
import { SettingsSection } from "./SettingsSection";
import { cn } from "@/lib/utils";

const POLL_MS = 3000;

const KIND_ORDER = ["memory", "message", "artifact", "env_var", "skill"] as const;

function kindRemaining(counts: EmbeddingStateCounts): number {
  return (counts.pending ?? 0) + (counts.failed ?? 0);
}

function ProgressBar({ percent }: { percent: number | null }) {
  const value = percent ?? 0;
  return (
    <div className="h-2 overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

function KindRow({
  kind,
  counts,
  queueCount,
}: {
  kind: (typeof KIND_ORDER)[number];
  counts: EmbeddingStateCounts;
  queueCount: number;
}) {
  const { t } = useTranslation();
  const remaining = kindRemaining(counts);
  const indexable = (counts.ready ?? 0) + remaining;
  const percent = indexable > 0 ? Math.round(((counts.ready ?? 0) / indexable) * 100) : null;

  return (
    <div className="grid grid-cols-[minmax(0,8rem)_1fr_auto] items-center gap-3 border-b border-border/60 py-2.5 last:border-0">
      <span className="text-sm">{t(`settings.embedding.kinds.${kind}`)}</span>
      <ProgressBar percent={percent} />
      <span className="min-w-[5.5rem] text-right text-xs tabular-nums text-muted-foreground">
        {remaining > 0
          ? t("settings.embedding.rowRemaining", { count: remaining })
          : t("settings.embedding.rowDone")}
        {queueCount > 0 ? ` · ${t("settings.embedding.queueShort", { count: queueCount })}` : ""}
      </span>
    </div>
  );
}

export function SettingsEmbeddingPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<EmbeddingProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();

    const load = async (silent = false) => {
      try {
        const result = await getEmbeddingProgress(ac.signal);
        setData(result);
        setError(null);
      } catch (e) {
        if (ac.signal.aborted) return;
        if (!silent) setError((e as Error).message);
      } finally {
        if (!ac.signal.aborted && !silent) setLoading(false);
      }
    };

    void load();
    const timer = window.setInterval(() => void load(true), POLL_MS);

    return () => {
      ac.abort();
      clearInterval(timer);
    };
  }, []);

  const summary = data?.summary;
  const queue = data?.queue;
  const skillReindex = data?.skill_reindex;
  const idle = data && !data.active;
  const empty = summary && summary.indexable === 0;

  return (
    <div className="space-y-4">
      <SettingsSection title={t("settings.embedding.overall.title")} description={t("settings.embedding.overall.description")}>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            {t("settings.embedding.loading")}
          </div>
        )}
        {!loading && error && <p className="text-sm text-destructive">{error}</p>}
        {!loading && !error && data && (
          <div className="space-y-3">
            {empty ? (
              <p className="text-sm text-muted-foreground">{t("settings.embedding.empty")}</p>
            ) : (
              <>
                <div className="space-y-2">
                  <div className="flex items-baseline justify-between gap-3">
                    <span
                      className={cn(
                        "text-2xl font-semibold tabular-nums",
                        idle ? "text-muted-foreground" : "text-foreground",
                      )}
                    >
                      {summary?.percent != null ? `${summary.percent}%` : "—"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {idle
                        ? t("settings.embedding.statusIdle")
                        : t("settings.embedding.statusActive")}
                    </span>
                  </div>
                  <ProgressBar percent={summary?.percent ?? null} />
                  <p className="text-xs text-muted-foreground">
                    {t("settings.embedding.summaryLine", {
                      ready: summary?.ready ?? 0,
                      remaining: summary?.remaining ?? 0,
                      skipped: summary?.skipped ?? 0,
                    })}
                  </p>
                </div>

                {(queue?.queued ?? 0) > 0 || (queue?.retry_waiting ?? 0) > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    {t("settings.embedding.queueDetail", {
                      queued: queue?.queued ?? 0,
                      retry: queue?.retry_waiting ?? 0,
                    })}
                  </p>
                ) : null}

                {(skillReindex?.pending_skills ?? 0) > 0 || skillReindex?.full_reindex ? (
                  <p className="text-xs text-muted-foreground">
                    {skillReindex?.full_reindex
                      ? t("settings.embedding.skillFullReindex")
                      : t("settings.embedding.skillPending", {
                          count: skillReindex?.pending_skills ?? 0,
                        })}
                  </p>
                ) : null}
              </>
            )}
          </div>
        )}
      </SettingsSection>

      {!loading && !error && data && !empty ? (
        <SettingsSection title={t("settings.embedding.byKind.title")}>
          {KIND_ORDER.map((kind) => (
            <KindRow
              key={kind}
              kind={kind}
              counts={data.by_kind[kind] ?? { pending: 0, ready: 0, failed: 0, skipped: 0 }}
              queueCount={data.queue.by_kind[kind] ?? 0}
            />
          ))}
        </SettingsSection>
      ) : null}
    </div>
  );
}
