import type { ReactNode } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { ListCard } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { findScrollParent } from "@/lib/scroll-parent";
import { usePinnedCollapse } from "@/lib/use-pinned-collapse";

export function toggleWithScrollPreservation(toggle: () => void, triggerEl: HTMLButtonElement) {
  const scroller = findScrollParent(triggerEl);
  const prevTop = scroller?.scrollTop ?? 0;
  toggle();
  requestAnimationFrame(() => {
    if (scroller) scroller.scrollTop = prevTop;
    setTimeout(() => {
      if (scroller) scroller.scrollTop = prevTop;
    }, 0);
  });
}

function BlockLeading({ running, icon }: { running: boolean; icon: ReactNode }) {
  return (
    <span
      className={cn(
        "flex size-6 shrink-0 items-center justify-center rounded-md",
        running ? "bg-brand/10 text-brand" : "bg-muted text-muted-foreground",
      )}
    >
      {running ? <Loader2 className="size-3.5 animate-spin" /> : icon}
    </span>
  );
}

export function CollapsibleMetaBlock({
  blockId,
  active = false,
  lockWhenActive = true,
  title,
  activeTitle,
  running = false,
  showRunningBadge = false,
  icon,
  preview,
  hidePreviewWhenOpen = true,
  trailing,
  children,
  className,
}: {
  blockId: string;
  /** 进行中：默认展开；lockWhenActive 为 true 时强制展开且不可折叠 */
  active?: boolean;
  /** 进行中是否锁定为展开；工具块为 true，todo 卡片为 false */
  lockWhenActive?: boolean;
  title: string;
  activeTitle?: string;
  running?: boolean;
  showRunningBadge?: boolean;
  icon: ReactNode;
  preview?: string;
  /** 展开时是否隐藏标题栏 preview；thinking 默认隐藏，工具参数需保持可见 */
  hidePreviewWhenOpen?: boolean;
  trailing?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const [open, toggleOpen] = usePinnedCollapse(blockId, false);
  const isOpen = lockWhenActive && active ? true : open;
  const expandable = Boolean(children) && (!lockWhenActive || !active);
  const displayTitle = running && activeTitle ? activeTitle : title;
  const previewText = preview?.replace(/\s+/g, " ").trim();
  const showPreview = Boolean(previewText) && (!isOpen || !hidePreviewWhenOpen);

  return (
    <ListCard className={cn("my-1.5 overflow-hidden p-0", className)}>
      <button
        type="button"
        disabled={!expandable}
        onClick={(e) => {
          if (!expandable) return;
          toggleWithScrollPreservation(toggleOpen, e.currentTarget);
        }}
        className={cn(
          "flex w-full min-w-0 items-center gap-2 px-3.5 py-2.5 text-left transition-colors",
          expandable && "hover:bg-surface/60",
        )}
      >
        <BlockLeading running={running} icon={icon} />
        <span className="shrink-0 whitespace-nowrap text-[13px] font-medium text-foreground">{displayTitle}</span>
        {showRunningBadge && running ? (
          <span className="shrink-0 rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] font-medium text-brand">
            执行中
          </span>
        ) : null}
        {showPreview ? (
          <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground/50">{previewText}</span>
        ) : (
          <span className="min-w-0 flex-1" aria-hidden />
        )}
        {trailing}
        {expandable ? (
          <ChevronRight
            className={cn(
              "size-3.5 shrink-0 text-muted-foreground transition-transform duration-150",
              isOpen && "rotate-90",
            )}
          />
        ) : null}
      </button>
      {isOpen && children ? (
        <div className="border-t border-border bg-surface/30 px-3.5 py-3">{children}</div>
      ) : null}
    </ListCard>
  );
}
