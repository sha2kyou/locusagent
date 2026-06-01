import { NavLink } from "react-router-dom";
import { Package } from "lucide-react";
import { cn } from "@/lib/utils";

const rowBase =
  "group relative flex h-10 items-center gap-3 rounded-lg px-2.5 text-sm font-medium transition-colors";

export function ArtifactsNav({
  basePrefix,
  expanded,
  onNavigate,
}: {
  basePrefix: string;
  expanded: boolean;
  onNavigate: () => void;
}) {
  return (
    <NavLink
      to={`${basePrefix}/artifacts`}
      title="产物"
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          rowBase,
          !expanded && "md:justify-center",
          isActive
            ? "bg-sidebar-accent text-foreground"
            : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
        )
      }
    >
      <Package className="size-[18px] shrink-0" />
      <span className={cn("truncate", !expanded && "md:hidden")}>产物</span>
    </NavLink>
  );
}
