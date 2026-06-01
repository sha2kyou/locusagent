import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SecondarySidebar({
  mobileOpen = false,
  onClose,
  children,
}: {
  mobileOpen?: boolean;
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
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-surface transition-transform duration-200 md:bg-surface/30",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          "md:static md:z-auto md:w-64 md:translate-x-0",
        )}
      >
        {children}
      </aside>
    </>
  );
}
