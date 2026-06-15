import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { getBackendLogs } from "@/api/endpoints";
import type { BackendLogs } from "@/api/types";

const POLL_MS = 3000;
const MAX_LINES = 2000;

export function SettingsLogsPage() {
  const [data, setData] = useState<BackendLogs | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  useEffect(() => {
    const ac = new AbortController();

    const load = async (silent = false) => {
      try {
        const result = await getBackendLogs({ lines: MAX_LINES }, ac.signal);
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

  useEffect(() => {
    if (pinnedRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }
  }, [data]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  return (
    <div className="space-y-2">
      {data?.path && (
        <p className="font-mono text-xs text-muted-foreground">{data.path}</p>
      )}

      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-[min(72vh,44rem)] overflow-y-auto rounded-lg border border-border bg-[#0d0d0d] p-3 font-mono text-xs leading-5 text-green-400"
      >
        {loading && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            加载中…
          </div>
        )}
        {!loading && error && (
          <span className="text-destructive">{error}</span>
        )}
        {!loading && !error && (!data || data.lines.length === 0) && (
          <span className="text-muted-foreground">暂无日志。</span>
        )}
        {!loading && !error && data && data.lines.length > 0 &&
          data.lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              {line || "\u00a0"}
            </div>
          ))
        }
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
