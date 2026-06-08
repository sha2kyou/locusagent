import { cn } from "@/lib/utils";

export const secondarySidebarHeaderClass =
  "shrink-0 space-y-2.5 border-b border-sidebar-sub-border/45 px-3 pb-3 pt-1";

export const secondarySidebarHeaderTitleRowClass = "flex h-11 items-center gap-2 px-1";

export const secondarySidebarTitleClass =
  "min-w-0 flex-1 text-[14px] font-bold tracking-tight";

export const secondarySidebarScrollClass = "flex-1 overflow-y-auto px-2 pb-3 pt-2";

export const secondarySidebarSkeletonWrapClass = "space-y-1.5 px-1 py-2";

export const secondarySidebarListClass = "space-y-1";

export const secondarySidebarGroupClass = "mb-3 last:mb-0";

export const secondarySidebarGroupLabelClass =
  "px-2.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50";

export function secondarySidebarRowClass(isActive: boolean) {
  return cn(
    "flex min-h-9 items-center gap-1 rounded-lg px-2.5 py-2 text-[13px] transition-colors",
    isActive
      ? "bg-sidebar-sub-accent font-medium text-foreground shadow-xs"
      : "text-muted-foreground hover:bg-sidebar-sub-accent/70 hover:text-foreground/90",
  );
}

export const secondarySidebarRowLabelClass =
  "min-w-0 flex-1 truncate text-left leading-snug";

export const secondarySidebarRowActionsClass =
  "flex shrink-0 items-center gap-0.5";
