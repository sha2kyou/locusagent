import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
  showClose?: boolean;
  closeDisabled?: boolean;
}

const sizes = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-xl",
};

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  showClose = true,
  closeDisabled = false,
}: ModalProps) {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const closeDisabledRef = useRef(closeDisabled);
  onCloseRef.current = onClose;
  closeDisabledRef.current = closeDisabled;

  const focusables = () =>
    Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])',
      ) ?? [],
    ).filter((el) => el.offsetParent !== null);

  // 仅在打开时聚焦一次；勿依赖 onClose，否则父组件重渲染会反复抢焦点
  useEffect(() => {
    if (!open) return;
    const prevFocus = document.activeElement as HTMLElement | null;
    const first = focusables()[0];
    (first ?? dialogRef.current)?.focus();
    return () => {
      prevFocus?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (!closeDisabledRef.current) onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && active === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
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
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/40 apod-fade"
        onClick={() => {
          if (!closeDisabled) onClose();
        }}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          "relative flex max-h-[calc(100dvh-2rem)] w-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xl apod-enter-up",
          sizes[size],
        )}
      >
        {(title || showClose) && (
          <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border/45 px-5 py-4">
            <div className="min-w-0 space-y-1">
              {title && (
                <h2 className="text-[15px] font-semibold tracking-tight text-foreground">{title}</h2>
              )}
              {description && (
                <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
              )}
            </div>
            {showClose && !closeDisabled && (
              <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("common.close")}>
                <X />
              </Button>
            )}
          </div>
        )}
        {children ? (
          <div className="min-h-0 overflow-y-auto px-5 py-4">{children}</div>
        ) : null}
        {footer && (
          <div className="flex shrink-0 justify-end gap-2 border-t border-border/45 px-5 py-4">{footer}</div>
        )}
      </div>
    </div>,
    document.body,
  );
}
