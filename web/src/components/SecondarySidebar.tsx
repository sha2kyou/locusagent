import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SecondarySidebar({
  mobileOpen = false,
  mobileSide = "left",
  onClose,
  children,
}: {
  mobileOpen?: boolean;
  mobileSide?: "left" | "right";
  onClose?: () => void;
  children: ReactNode;
}) {
  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={onClose} />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 z-50 flex w-72 flex-col bg-surface transition-transform duration-200 md:static md:z-auto md:w-64 md:translate-x-0 md:border-r md:border-border md:bg-surface/30",
          mobileSide === "right"
            ? mobileOpen
              ? "right-0 border-l border-border translate-x-0"
              : "right-0 border-l border-border translate-x-full"
            : mobileOpen
              ? "left-0 border-r border-border translate-x-0"
              : "left-0 border-r border-border -translate-x-full",
        )}
      >
        {children}
      </aside>
    </>
  );
}
