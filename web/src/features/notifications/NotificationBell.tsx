import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Bell, BrushCleaning, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useNotifications } from "./NotificationProvider";
import type { NotificationEntry } from "@/api/types";

const PANEL_WIDTH = 352;
const VIEWPORT_GAP = 8;

function formatWhen(iso: string): string {
  const d = new Date(iso).getTime();
  const diff = Date.now() - d;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return "刚刚";
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`;
  return new Date(iso).toLocaleString();
}

function computePanelPos(anchor: DOMRect, align: "start" | "end") {
  const width = Math.min(PANEL_WIDTH, window.innerWidth - VIEWPORT_GAP * 2);
  let left: number;
  if (align === "end") {
    left = anchor.right - width;
  } else {
    left = anchor.left;
  }
  left = Math.max(VIEWPORT_GAP, Math.min(left, window.innerWidth - width - VIEWPORT_GAP));
  return {
    top: anchor.bottom + VIEWPORT_GAP,
    left,
    width,
  };
}

function displayCategory(item: NotificationEntry): string | null {
  if (item.category) return item.category;
  if (item.title.startsWith("产物已保存：")) return "保存产物";
  return null;
}

function displayTitle(item: NotificationEntry): string {
  if (item.category) return item.title;
  const prefix = "产物已保存：";
  if (item.title.startsWith(prefix)) return item.title.slice(prefix.length);
  return item.title;
}

function NotificationRow({
  item,
  onOpen,
}: {
  item: NotificationEntry;
  onOpen: () => void;
}) {
  const category = displayCategory(item);
  const title = displayTitle(item);
  return (
    <div
      className="group flex gap-1 rounded-lg transition-colors hover:bg-surface/80"
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        onOpen();
      }}
    >
      <div className="min-w-0 flex-1 px-3 py-2.5 text-left">
        <div className="flex items-start justify-between gap-2">
          {category ? (
            <span className="text-[11px] leading-5 text-muted-foreground">{category}</span>
          ) : (
            <span />
          )}
          <span className="shrink-0 text-[11px] leading-5 text-muted-foreground">
            {formatWhen(item.created_at)}
          </span>
        </div>
        <p className="mt-1 text-sm leading-snug text-foreground">
          {title}
        </p>
        {item.body ? (
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.body}</p>
        ) : null}
      </div>
    </div>
  );
}

export function NotificationBell({
  className,
  menuAlign = "end",
}: {
  className?: string;
  /** start：左对齐向右展开（侧栏）；end：右对齐向左展开（顶栏右侧） */
  menuAlign?: "start" | "end";
}) {
  const navigate = useNavigate();
  const { items, unreadCount, loading, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number; width: number } | null>(null);

  const updatePanelPos = () => {
    const anchor = rootRef.current?.getBoundingClientRect();
    if (!anchor) return;
    setPanelPos(computePanelPos(anchor, menuAlign));
  };

  useLayoutEffect(() => {
    if (!open) {
      setPanelPos(null);
      return;
    }
    updatePanelPos();
    window.addEventListener("resize", updatePanelPos);
    window.addEventListener("scroll", updatePanelPos, true);
    return () => {
      window.removeEventListener("resize", updatePanelPos);
      window.removeEventListener("scroll", updatePanelPos, true);
    };
  }, [open, menuAlign]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const onOpenItem = async (item: NotificationEntry) => {
    if (!item.read) await markRead(item.id);
    if (item.link) {
      navigate(item.link);
      setOpen(false);
    }
  };

  const panel =
    open && panelPos
      ? createPortal(
          <div
            ref={panelRef}
            style={{ top: panelPos.top, left: panelPos.left, width: panelPos.width }}
            className="fixed z-200 overflow-hidden rounded-xl border border-border-strong bg-card text-card-foreground shadow-2xl apod-enter-up"
          >
            <div className="flex items-center justify-between border-b border-border bg-surface px-3.5 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">消息</span>
                {unreadCount > 0 && (
                  <span className="rounded-full bg-brand px-1.5 py-0.5 text-[10px] font-semibold leading-none text-brand-foreground">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-0.5">
                {unreadCount > 0 ? (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => void markAllRead()}
                    aria-label="全部标记为已读"
                    title="全部已读"
                  >
                    <BrushCleaning className="size-4" />
                  </Button>
                ) : null}
                <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)} aria-label="关闭">
                  <X className="size-4" />
                </Button>
              </div>
            </div>

            <div className="max-h-[min(24rem,60vh)] overflow-y-auto bg-card p-1.5">
              {loading && items.length === 0 ? (
                <p className="px-3 py-10 text-center text-sm text-muted-foreground">加载中…</p>
              ) : items.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-3 py-10 text-center">
                  <Bell className="size-8 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">暂无消息</p>
                </div>
              ) : (
                <div className="flex flex-col gap-1">
                  {items.map((item) => (
                    <NotificationRow
                      key={item.id}
                      item={item}
                      onOpen={() => void onOpenItem(item)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <div ref={rootRef} className={cn("relative", className)}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label="消息通知"
          aria-expanded={open}
          className={cn(
            "relative inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-secondary hover:text-foreground",
            open && "bg-secondary text-foreground",
          )}
        >
          <Bell className="size-5" />
          {unreadCount > 0 && (
            <span className="absolute right-1 top-1 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-4 text-white">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </button>
      </div>
      {panel}
    </>
  );
}
