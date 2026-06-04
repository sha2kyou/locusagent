import { useMemo } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { SessionMeta } from "@/api/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/ui/search-input";
import { SidebarEmpty } from "@/components/ui/list-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useDialogs } from "@/components/ui/dialogs";
import { useToast } from "@/components/ui/toast";
import { useChat } from "./ChatProvider";
import { SecondarySidebar } from "@/components/SecondarySidebar";

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

function sessionLabel(title: string): string {
  return title.trim() || "新对话";
}

export function SessionSidebar({
  mobileOpen = false,
  onClose,
}: {
  mobileOpen?: boolean;
  onClose?: () => void;
}) {
  const { sessions, loadingSessions, hasMoreSessions, loadingMoreSessions, loadMoreSessions, currentId, query, setQuery, newSession, selectSession, deleteSession } = useChat();
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
  const filteredSessions = useMemo(
    () => groups.flatMap((g) => g.items),
    [groups],
  );

  const onDelete = async (s: SessionMeta) => {
    const label = sessionLabel(s.title);
    const ok = await confirm({
      title: "删除对话",
      body: `确定删除「${label}」？此操作不可恢复。`,
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

  const deleteAllVisible = async () => {
    if (filteredSessions.length === 0) return;
    const q = query.trim();
    const ok = await confirm({
      title: "删除全部对话",
      body: q
        ? `确定删除当前搜索结果中的 ${filteredSessions.length} 个对话？此操作不可恢复。`
        : `确定删除全部 ${filteredSessions.length} 个对话？此操作不可恢复。`,
      danger: true,
      confirmText: "删除",
    });
    if (!ok) return;
    try {
      const ids = filteredSessions.map((s) => s.id);
      const ordered =
        currentId && ids.includes(currentId)
          ? [...ids.filter((id) => id !== currentId), currentId]
          : ids;
      let failed = 0;
      for (const id of ordered) {
        try {
          await deleteSession(id, { silent: true });
        } catch {
          failed++;
        }
      }
      if (failed > 0) {
        toast(`已删除 ${ids.length - failed} 个，失败 ${failed} 个`, "error");
      } else {
        toast(`已删除 ${ids.length} 个对话`, "success");
      }
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <SecondarySidebar mobileOpen={mobileOpen} mobileSide="right" onClose={onClose}>
      <div className="p-3">
        <div className="flex items-center gap-2">
          <Button variant="primary" className="flex-1" onClick={handleNew}>
            <Plus className="size-4" /> 新对话
          </Button>
          <Button
            variant="secondary"
            size="icon-sm"
            disabled={filteredSessions.length === 0}
            onClick={() => {
              void deleteAllVisible();
            }}
            title="删除全部"
            aria-label="删除全部"
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>
      <div className="px-3 pb-2">
        <SearchInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索对话…"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {loadingSessions ? (
          <div className="space-y-1.5 px-1 py-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <SidebarEmpty text={query ? "无匹配对话" : "暂无对话"} />
        ) : (
          <>
            {groups.map((g) => (
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
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSelect(s.id)}
                    onKeyDown={(e) => {
                      if (e.key !== "Enter" && e.key !== " ") return;
                      e.preventDefault();
                      handleSelect(s.id);
                    }}
                  >
                    <span className="min-w-0 flex-1 truncate text-left" title={s.title}>
                      {sessionLabel(s.title)}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        void onDelete(s);
                      }}
                      aria-label="删除"
                    >
                      <Trash2 />
                    </Button>
                  </div>
                ))}
              </div>
            ))}
            {hasMoreSessions && !query && (
              <div className="px-2 py-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full text-xs text-muted-foreground/70"
                  onClick={() => void loadMoreSessions()}
                  disabled={loadingMoreSessions}
                >
                  {loadingMoreSessions ? "加载中…" : "加载更多"}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </SecondarySidebar>
  );
}
