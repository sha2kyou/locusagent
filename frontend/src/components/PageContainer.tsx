import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  /** 嵌入双栏布局主区时省略外层滚动壳 */
  embedded?: boolean;
  className?: string;
}

export function PageContainer({
  title,
  subtitle,
  actions,
  children,
  embedded = false,
  className,
}: Props) {
  const inner = (
    <div className={cn("mx-auto w-full max-w-3xl px-6 py-10", className)}>
      <header className="mb-6 flex items-end justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {actions}
      </header>
      {children}
    </div>
  );
  if (embedded) return inner;
  return <div className="h-full overflow-y-auto">{inner}</div>;
}
