import { cn } from "@/lib/utils";

/** 与 public/favicon.svg 同一套 Bot 图形 */
const BRAND_BOT_PATHS = (
  <>
    <path d="M11 12h.01" />
    <path d="M13 22c.5-.5 1.12-1 2.5-1-1.38 0-2-.5-2.5-1" />
    <path d="M14 2a3.28 3.28 0 0 1-3.227 1.798l-6.17-.561A2.387 2.387 0 1 0 4.387 8H15.5a1 1 0 0 1 0 13 1 1 0 0 0 0-5H12a7 7 0 0 1-7-7V8" />
    <path d="M14 8a8.5 8.5 0 0 1 0 8" />
    <path d="M16 16c2 0 4.5-4 4-6" />
  </>
);

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-5", className)}
      aria-hidden="true"
    >
      {BRAND_BOT_PATHS}
    </svg>
  );
}
