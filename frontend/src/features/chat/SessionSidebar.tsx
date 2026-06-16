import { useMemo } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { SessionMeta } from "@/api/types";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/ui/search-input";
import { SidebarEmpty } from "@/components/ui/list-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useDialogs } from "@/components/ui/dialogs";
import { useToast } from "@/components/ui/toast";
import { useChat } from "./ChatProvider";
import { SecondarySidebar } from "@/components/SecondarySidebar";
import {
  SecondarySidebarHeader,
  SecondarySidebarListRow,
} from "@/components/SecondarySidebarList";
import {
  secondarySidebarGroupClass,
  secondarySidebarGroupLabelClass,
  secondarySidebarListClass,
  secondarySidebarScrollClass,
  secondarySidebarSkeletonWrapClass,
} from "@/components/secondary-sidebar-styles";
import { SESSION_LIST_GROUP_ORDER } from "@/lib/format-time";
import { useTimeFormatters } from "@/lib/use-app-timezone";

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
  const { sessionListGroupLabel } = useTimeFormatters();

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
      const key = sessionListGroupLabel(s.updated_at || s.created_at);
      (map.get(key) ?? map.set(key, []).get(key)!).push(s);
    }
    return SESSION_LIST_GROUP_ORDER.filter((k) => map.has(k)).map((k) => ({
      label: k,
      items: map.get(k)!,
    }));
  }, [sessions, query, sessionListGroupLabel]);

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

  return (
    <SecondarySidebar mobileOpen={mobileOpen} mobileSide="right" onClose={onClose}>
      <SecondarySidebarHeader
        title="对话"
        actions={
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={handleNew}
            title="新对话"
            aria-label="新对话"
          >
            <Plus className="size-4" />
          </Button>
        }
        search={
          <SearchInput
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索对话…"
          />
        }
      />

      <div className={secondarySidebarScrollClass}>
        {loadingSessions ? (
          <div className={secondarySidebarSkeletonWrapClass}>
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <SidebarEmpty text={query ? "无匹配对话" : "暂无对话"} />
        ) : (
          <>
            {groups.map((g) => (
              <div key={g.label} className={secondarySidebarGroupClass}>
                <div className={secondarySidebarGroupLabelClass}>{g.label}</div>
                <div className={secondarySidebarListClass}>
                  {g.items.map((s) => (
                    <SecondarySidebarListRow
                      key={s.id}
                      active={s.id === currentId}
                      label={sessionLabel(s.title)}
                      title={s.title}
                      onClick={() => handleSelect(s.id)}
                      actions={
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => {
                            void onDelete(s);
                          }}
                          aria-label="删除"
                        >
                          <Trash2 />
                        </Button>
                      }
                    />
                  ))}
                </div>
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
