import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const tagClass =
  "rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground transition hover:bg-secondary/80";

export function Tag({
  children,
  onClick,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={cn(tagClass, className)}>
        {children}
      </button>
    );
  }
  return <span className={cn(tagClass, className)}>{children}</span>;
}
