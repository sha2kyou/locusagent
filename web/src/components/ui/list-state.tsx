import { SkeletonList } from "@/components/ui/skeleton";

export function Loading() {
  return <SkeletonList rows={5} />;
}

export function Empty({ text }: { text: string }) {
  return <p className="py-8 text-center text-sm text-muted-foreground">{text}</p>;
}

export function SidebarEmpty({ text }: { text: string }) {
  return <p className="px-2 py-4 text-center text-xs text-muted-foreground">{text}</p>;
}

/** 列表行内操作按钮：hover 时显示，与二级侧栏一致 */
export const listRowHoverActionsClass =
  "shrink-0 opacity-0 transition-opacity group-hover:opacity-100";

/** 列表卡片内副标题/摘要 */
export const listItemDescriptionClass =
  "mt-1 line-clamp-2 text-sm text-muted-foreground";

/** 列表卡片单行摘要（仅一行） */
export const listItemBriefClass =
  "mt-1 line-clamp-1 text-sm text-muted-foreground";
