import { useMemo } from "react";
import { Plus, Search, Trash2 } from "lucide-react";
import type { SessionMeta } from "@/api/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useDialogs } from "@/components/ui/dialogs";
import { useToast } from "@/components/ui/toast";
import { useChat } from "./ChatProvider";

function groupLabel(iso: string): string {
  const d = new Date(iso).getTime();
  const now = Date.now();
  const day = 86400000;
  const diff = now - d;
  if (diff < day) return "今天";
  if (diff < 2 * day) return "昨天";
  if (diff < 7 * day) return "过去 7 天";
  if (diff < 30 * day) return "过去 30 天";
  return "更早";
}

const ORDER = ["今天", "昨天", "过去 7 天", "过去 30 天", "更早"];

export function SessionSidebar({
  mobileOpen = false,
  onClose,
}: {
  mobileOpen?: boolean;
  onClose?: () => void;
}) {
  const { sessions, loadingSessions, currentId, query, setQuery, newSession, selectSession, deleteSession } = useChat();
  const { confirm } = useDialogs();
  const toast = useToast();

  const handleSelect = (id: string) => {
    selectSession(id);
    onClose?.();
  };
  const handleNew = () => {
    newSession();
    onClose?.();
  };

  const groups = useMemo(() => {
    const filtered = sessions.filter((s) =>
      query.trim() ? s.title.toLowerCase().includes(query.trim().toLowerCase()) : true,
    );
    const map = new Map<string, SessionMeta[]>();
    for (const s of filtered) {
      const key = groupLabel(s.updated_at || s.created_at);
      (map.get(key) ?? map.set(key, []).get(key)!).push(s);
    }
    return ORDER.filter((k) => map.has(k)).map((k) => ({ label: k, items: map.get(k)! }));
  }, [sessions, query]);

  const onDelete = async (s: SessionMeta) => {
    const ok = await confirm({
      title: "删除会话",
      body: `确定删除「${s.title}」？此操作不可恢复。`,
      danger: true,
      confirmText: "删除",
    });
    if (!ok) return;
    try {
      await deleteSession(s.id);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <>
      {/* 移动端遮罩 */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={onClose} />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-surface transition-transform duration-200 md:bg-surface/30",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          "md:static md:z-auto md:w-64 md:translate-x-0",
        )}
      >
      <div className="p-3">
        <Button variant="primary" className="w-full" onClick={handleNew}>
          <Plus className="size-4" /> 新对话
        </Button>
      </div>
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索会话…"
            className="pl-8"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {loadingSessions ? (
          <div className="space-y-1.5 px-1 py-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            {query ? "无匹配会话" : "暂无会话"}
          </p>
        ) : (
          groups.map((g) => (
            <div key={g.label} className="mb-2">
              <div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/60">
                {g.label}
              </div>
              {g.items.map((s) => (
                <div
                  key={s.id}
                  className={cn(
                    "group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors",
                    s.id === currentId ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => handleSelect(s.id)}
                    className="min-w-0 flex-1 truncate text-left"
                    title={s.title}
                  >
                    {s.title || "新对话"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(s)}
                    className="shrink-0 rounded p-1 text-muted-foreground opacity-100 transition hover:text-destructive md:opacity-0 md:group-hover:opacity-100"
                    aria-label="删除"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
      </aside>
    </>
  );
}
