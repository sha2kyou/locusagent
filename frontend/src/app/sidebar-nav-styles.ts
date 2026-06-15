import { cn } from "@/lib/utils";

/** 侧栏宽度（桌面展开由 220px 收窄约 30% → 154px） */
export const sidebarPrimaryWidthClass = {
  expanded: "md:w-[154px]",
  collapsed: "md:w-[60px]",
  mobile: "w-[186px]",
} as const;

export const sidebarPrimaryOffsetClass = {
  expanded: "md:left-[154px]",
  collapsed: "md:left-[60px]",
} as const;

/** 收起侧栏 60px、36px 行居中时，18px 图标左缘距侧栏左缘 21px（13px 容器 + 8px 行内） */
export function sidebarNavContainerClass(expanded: boolean) {
  return cn(
    "flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-2",
    expanded && "md:px-[13px]",
    !expanded && "md:items-center md:px-0",
  );
}

/** 侧栏导航行：统一高度、间距与 active/hover 态 */
export function sidebarNavRowClass(isActive: boolean, expanded: boolean) {
  return cn(
    "flex min-h-9 w-full items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] font-medium leading-normal transition-colors",
    !expanded && "md:mx-auto md:h-9 md:w-9 md:justify-center md:gap-0 md:px-0 md:py-0",
    isActive
      ? "bg-sidebar-accent text-foreground"
      : "text-muted-foreground/75 hover:bg-sidebar-accent/50 hover:text-foreground",
  );
}

/** 固定宽度图标槽，保证文字起始位置一致 */
export const sidebarNavIconSlotClass = "flex w-[18px] shrink-0 items-center justify-center";

export const sidebarNavIconClass = "size-[18px] shrink-0";

export function sidebarNavLabelClass(expanded: boolean) {
  return cn("min-w-0 truncate leading-normal", !expanded && "md:hidden");
}

/** 分组线距侧栏左右边距（收起 60px + 居中 w-6 → 18px；展开 nav 13px + 分割线 5px） */
export function sidebarNavGroupDividerClass(expanded: boolean) {
  return cn(
    "flex w-full shrink-0 items-center my-2.5",
    expanded && "md:px-[5px]",
    !expanded && "hidden md:flex md:justify-center",
  );
}

export function sidebarNavGroupDividerLineClass(expanded: boolean) {
  return cn("h-px bg-sidebar-border/55", expanded ? "w-full" : "w-6");
}
