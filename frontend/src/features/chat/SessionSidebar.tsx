import { useMemo } from "react";
import { useTranslation } from "react-i18next";
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
import { displaySessionTitle } from "@/lib/session-title";
import { useTimeFormatters } from "@/lib/use-app-timezone";

export function SessionSidebar({
  mobileOpen = false,
  onClose,
}: {
  mobileOpen?: boolean;
  onClose?: () => void;
}) {
  const { t } = useTranslation();
  const { sessions, loadingSessions, hasMoreSessions, loadingMoreSessions, loadMoreSessions, currentId, query, setQuery, newSession, selectSession, deleteSession } = useChat();
  const { confirm } = useDialogs();
  const toast = useToast();
  const { sessionListGroupKey } = useTimeFormatters();

  const sessionLabel = (title: string) => displaySessionTitle(title, t);

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
      const key = sessionListGroupKey(s.updated_at || s.created_at);
      (map.get(key) ?? map.set(key, []).get(key)!).push(s);
    }
    return SESSION_LIST_GROUP_ORDER.filter((k) => map.has(k)).map((k) => ({
      label: t(`time.sessionGroups.${k}`),
      items: map.get(k)!,
    }));
  }, [sessions, query, sessionListGroupKey, t]);

  const onDelete = async (s: SessionMeta) => {
    const label = sessionLabel(s.title);
    const ok = await confirm({
      title: t("chat.session.deleteTitle"),
      body: t("chat.session.deleteBody", { label }),
      danger: true,
      confirmText: t("common.actions.delete"),
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
        title={t("chat.sidebar.title")}
        actions={
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={handleNew}
            title={t("chat.sidebar.newSession")}
            aria-label={t("chat.sidebar.newSession")}
          >
            <Plus className="size-4" />
          </Button>
        }
        search={
          <SearchInput
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("chat.sidebar.searchPlaceholder")}
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
          <SidebarEmpty text={query ? t("chat.sidebar.noMatch") : t("chat.sidebar.empty")} />
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
                          aria-label={t("common.actions.delete")}
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
                  {loadingMoreSessions ? t("common.loading") : t("chat.sidebar.loadMore")}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </SecondarySidebar>
  );
}
