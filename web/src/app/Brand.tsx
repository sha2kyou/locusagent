import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  const imgClass = cn("size-5 shrink-0 rounded-sm object-contain", className);
  return <img src="/logo.png" alt="" className={imgClass} aria-hidden="true" />;
}
