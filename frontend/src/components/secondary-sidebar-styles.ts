import { cn } from "@/lib/utils";

export const secondarySidebarHeaderClass =
  "apod-secondary-sidebar-header shrink-0 space-y-2.5 px-3 pb-3 pt-1";

export const secondarySidebarHeaderTitleRowClass = "flex min-h-11 items-center gap-2 px-1 py-1";

export const secondarySidebarTitleClass =
  "min-w-0 flex-1 text-[14px] font-bold tracking-tight";

export const secondarySidebarScrollClass = "flex-1 overflow-y-auto px-2 pb-2 pt-1";

export const secondarySidebarSkeletonWrapClass = "space-y-1 px-1 py-1";

export const secondarySidebarListClass = "space-y-0.5";

export const secondarySidebarGroupClass = "mb-1.5 last:mb-0";

export const secondarySidebarGroupLabelClass =
  "px-2.5 pb-0.5 pt-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50";

export function secondarySidebarRowClass(isActive: boolean) {
  return cn(
    "group flex min-h-8 cursor-pointer select-none items-center gap-1.5 rounded-md px-2 py-1.5 text-[13px] leading-normal transition-colors",
    isActive
      ? "bg-sidebar-sub-accent font-medium text-foreground shadow-xs"
      : "text-muted-foreground hover:bg-sidebar-sub-accent/70 hover:text-foreground/90",
  );
}

export const secondarySidebarRowLabelClass =
  "min-w-0 flex-1 truncate text-left leading-normal";

export const secondarySidebarRowActionsClass =
  "flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100";
