import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-5", className)}
      aria-hidden="true"
    >
      <path d="M12 2 L4 7 v10 l8 5 l8-5 V7 z" />
      <path d="M12 22 V12" />
      <path d="M4 7 L12 12 L20 7" />
    </svg>
  );
}
