import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("size-5 shrink-0", className)}
      aria-hidden="true"
    >
      <g fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round">
        <circle cx="16" cy="16" r="9" />
        <line x1="8.5" y1="23.5" x2="23.5" y2="8.5" />
      </g>
    </svg>
  );
}
