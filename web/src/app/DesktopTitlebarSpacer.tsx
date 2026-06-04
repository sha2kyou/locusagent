import { useEffect } from "react";
import { desktopDragRegionProps, isDesktopApp } from "@/lib/desktop-app";

/** macOS 透明标题栏安全区；Web 端不渲染任何 DOM。 */
export function DesktopTitlebarSpacer() {
  const desktop = isDesktopApp();

  useEffect(() => {
    if (!desktop) return;
    document.documentElement.classList.add("apod-desktop");
    return () => document.documentElement.classList.remove("apod-desktop");
  }, [desktop]);

  if (!desktop) return null;

  return <div {...desktopDragRegionProps()} className="h-9 shrink-0" aria-hidden />;
}
