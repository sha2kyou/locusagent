import { cn } from "@/lib/utils";

/** 侧栏导航行：统一高度、间距与 active/hover 态 */
export function sidebarNavRowClass(isActive: boolean, expanded: boolean) {
  return cn(
    "flex h-9 w-full items-center gap-2 rounded-lg px-2 text-[13px] font-medium leading-none transition-colors",
    !expanded && "md:size-9 md:justify-center md:gap-0 md:px-0",
    isActive
      ? "bg-sidebar-accent text-foreground"
      : "text-muted-foreground/75 hover:bg-sidebar-accent/50 hover:text-foreground",
  );
}

/** 固定宽度图标槽，保证文字起始位置一致 */
export const sidebarNavIconSlotClass = "flex w-[18px] shrink-0 items-center justify-center";

export const sidebarNavIconClass = "size-[18px] shrink-0";

export function sidebarNavLabelClass(expanded: boolean) {
  return cn("min-w-0 truncate leading-none", !expanded && "md:hidden");
}

export function sidebarNavGroupLabelClass(expanded: boolean) {
  if (!expanded) return "mt-3 hidden md:block";
  // 与导航文字左缘对齐：px-2 + icon 槽 18px + gap-2
  return "mb-0.5 mt-4 pl-[calc(0.5rem+18px+0.5rem)] pr-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/35";
}
