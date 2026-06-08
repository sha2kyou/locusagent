import { useEffect, type HTMLAttributes, type MouseEvent as ReactMouseEvent } from "react";

export const DESKTOP_GATEWAY_ORIGIN = "http://127.0.0.1:1420";
/** 与 desktop gateway 默认 upstream（AGENTPOD_API_URL）一致 */
export const DESKTOP_API_ORIGIN = "http://127.0.0.1:1223";

export function isDesktopApp(): boolean {
  if (typeof window === "undefined") return false;
  return window.location.origin === DESKTOP_GATEWAY_ORIGIN;
}

/** 桌面壳根节点 class，供拖拽样式等全局规则使用 */
export function useDesktopAppHtmlClass(): void {
  useEffect(() => {
    if (!isDesktopApp()) return;
    document.documentElement.classList.add("apod-desktop");
    return () => document.documentElement.classList.remove("apod-desktop");
  }, []);
}

function isDesktopInteractiveTarget(el: HTMLElement): boolean {
  return (
    el.closest(
      'button, a, input, textarea, select, label, summary, [contenteditable="true"], [tabindex]:not([tabindex="-1"]), [role="button"], [role="link"], [role="menuitem"], [role="tab"], [role="checkbox"], [role="radio"], [role="switch"], [role="option"]',
    ) !== null
  );
}

async function startDesktopWindowDrag(): Promise<void> {
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().startDragging();
}

function onDesktopDragMouseDown(
  mode: "self" | "deep",
): NonNullable<HTMLAttributes<HTMLElement>["onMouseDown"]> {
  return (event: ReactMouseEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    if (mode === "self" && event.target !== event.currentTarget) return;
    if (mode === "deep" && isDesktopInteractiveTarget(event.target as HTMLElement)) return;
    event.preventDefault();
    void startDesktopWindowDrag();
  };
}

type DesktopDragRegionProps = HTMLAttributes<HTMLElement> &
  Partial<Record<"data-tauri-drag-region", string | boolean>>;

/** 桌面壳透明标题栏：供顶栏等区域拖拽移动窗口 */
export function desktopDragRegionProps(mode: "self" | "deep" = "self"): DesktopDragRegionProps {
  if (!isDesktopApp()) return {};
  return {
    "data-tauri-drag-region": mode === "deep" ? "deep" : true,
    onMouseDown: onDesktopDragMouseDown(mode),
  };
}
