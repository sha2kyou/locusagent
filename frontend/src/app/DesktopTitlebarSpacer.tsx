import { desktopDragRegionProps, isDesktopApp, useDesktopAppHtmlClass } from "@/lib/desktop-app";
import { cn } from "@/lib/utils";

type DesktopWindowDragOverlayProps = {
  /** 桌面侧栏展开时主内容区拖拽条 left 偏移（px） */
  mainOffsetClassName?: string;
};

/** macOS 透明标题栏：固定于窗口顶部的拖拽层，不占布局高度。Web 端不渲染。 */
export function DesktopWindowDragOverlay({ mainOffsetClassName }: DesktopWindowDragOverlayProps) {
  useDesktopAppHtmlClass();

  if (!isDesktopApp()) return null;

  return (
    <div
      {...desktopDragRegionProps()}
      className={cn(
        "pointer-events-auto fixed top-0 right-0 z-[60] h-7",
        mainOffsetClassName ?? "left-0",
      )}
      aria-hidden
    />
  );
}
