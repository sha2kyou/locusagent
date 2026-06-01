import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

export function SegmentControl<T extends string>({
  value,
  onChange,
  options,
  className,
  optionClassName,
}: {
  value: T;
  onChange: (value: T) => void;
  options: SegmentOption<T>[];
  className?: string;
  optionClassName?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex rounded-lg border border-border bg-surface/40 p-1",
        className,
      )}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          disabled={opt.disabled}
          onClick={() => onChange(opt.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
            value === opt.value
              ? "bg-secondary text-foreground"
              : "text-muted-foreground hover:text-foreground",
            optionClassName,
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
