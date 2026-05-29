import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
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
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prevFocus = document.activeElement as HTMLElement | null;

    const focusables = () =>
      Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => el.offsetParent !== null);

    // 打开后聚焦首个可聚焦元素（退化为对话框本身）
    const first = focusables()[0];
    (first ?? dialogRef.current)?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (!closeDisabled) onClose();
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
      prevFocus?.focus?.();
    };
  }, [open, onClose, closeDisabled]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/55 backdrop-blur-sm apod-fade"
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
          "relative w-full rounded-xl border border-border-strong bg-popover p-5 shadow-2xl apod-enter-up",
          sizes[size],
        )}
      >
        {(title || showClose) && (
          <div className="mb-3 flex items-start justify-between gap-4">
            <div className="space-y-1">
              {title && <h2 className="text-base font-semibold">{title}</h2>}
              {description && (
                <p className="text-sm text-muted-foreground">{description}</p>
              )}
            </div>
            {showClose && !closeDisabled && (
              <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭">
                <X />
              </Button>
            )}
          </div>
        )}
        {children}
        {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
