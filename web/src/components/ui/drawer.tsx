import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  width?: "md" | "lg" | "xl";
}

const widths = {
  md: "max-w-md",
  lg: "max-w-xl",
  xl: "max-w-2xl",
};

export function Drawer({
  open,
  onClose,
  title,
  description,
  actions,
  children,
  width = "lg",
}: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prevFocus = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prevFocus?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[90]">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-sm apod-fade" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          "absolute inset-y-0 right-0 flex w-full flex-col border-l border-border-strong bg-popover shadow-2xl apod-enter-right",
          widths[width],
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0 space-y-1">
            {title && <h2 className="truncate text-base font-semibold">{title}</h2>}
            {description && <p className="text-xs text-muted-foreground">{description}</p>}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {actions}
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭">
              <X />
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
