import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./button";
import { glassOverlayClass } from "./surface-styles";

/** Former drawer `lg` variant — not `xl` (`max-w-2xl`). */
const DRAWER_WIDTH = "max-w-xl";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}

export function Drawer({
  open,
  onClose,
  title,
  description,
  actions,
  children,
}: DrawerProps) {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const prevFocus = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => {
      prevFocus?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[90]">
      <div className={cn("absolute inset-0", glassOverlayClass)} onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          "absolute inset-y-0 right-0 flex w-full flex-col border-l border-border bg-background shadow-lg apod-enter-right",
          DRAWER_WIDTH,
        )}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border/45 px-4 py-3">
          <div className="min-w-0 space-y-0.5">
            {title && (
              <h2 className="truncate text-[14px] font-bold tracking-tight text-foreground">{title}</h2>
            )}
            {description && (
              <p className="truncate text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-0.5">
            {actions}
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("common.close")}>
              <X />
            </Button>
          </div>
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto px-4 py-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
