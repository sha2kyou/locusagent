import { useEffect, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export function CollapsiblePanel({
  summary,
  children,
  defaultOpen = false,
  onOpenChange,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => {
    setOpen(defaultOpen);
  }, [defaultOpen]);
  const toggle = () => {
    setOpen((v) => {
      const next = !v;
      onOpenChange?.(next);
      return next;
    });
  };
  return (
    <div className="rounded-xl border border-border bg-surface/40">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium"
      >
        {summary}
        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="border-t border-border p-4">{children}</div>}
    </div>
  );
}

/** 列表卡片内嵌折叠区，与 ListCard（p-0 overflow-hidden）配合使用 */
export function CollapsibleSection({
  summary,
  children,
  defaultOpen = false,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between border-t border-border px-4 py-2.5 text-left"
      >
        {typeof summary === "string" ? (
          <span className="text-xs text-muted-foreground">{summary}</span>
        ) : (
          summary
        )}
        <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="border-t border-border px-4 py-3">{children}</div>}
    </>
  );
}

export function ListCard({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border bg-surface/40 p-4", className)}>{children}</div>
  );
}
