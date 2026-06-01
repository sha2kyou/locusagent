import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ChevronDown, FolderOpen, Package } from "lucide-react";
import { cn } from "@/lib/utils";
import { listArtifactCategories } from "@/api/endpoints";
import type { ArtifactCategory } from "@/api/types";
import { stripWorkspacePrefix } from "@/app/workspace-route";

const CATEGORIES_CHANGED = "artifacts:categories-changed";

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
  const location = useLocation();
  const routePath = stripWorkspacePrefix(location.pathname).path;
  const onArtifacts = routePath.startsWith("/artifacts");
  const [open, setOpen] = useState(onArtifacts);
  const [categories, setCategories] = useState<ArtifactCategory[]>([]);

  const load = async () => {
    try {
      const { items } = await listArtifactCategories();
      setCategories(items);
    } catch {
      setCategories([]);
    }
  };

  useEffect(() => {
    void load();
    const onChange = () => void load();
    window.addEventListener(CATEGORIES_CHANGED, onChange);
    return () => window.removeEventListener(CATEGORIES_CHANGED, onChange);
  }, []);

  useEffect(() => {
    if (onArtifacts) setOpen(true);
  }, [onArtifacts]);

  return (
    <div>
      <div className="relative">
        <NavLink
          to={`${basePrefix}/artifacts/manage`}
          end
          title="产物"
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              rowBase,
              !expanded && "md:justify-center",
              expanded && categories.length > 0 && "pr-8",
              isActive
                ? "bg-sidebar-accent text-foreground"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
            )
          }
        >
          <Package className="size-[18px] shrink-0" />
          <span className={cn("truncate", !expanded && "md:hidden")}>产物</span>
        </NavLink>
        {expanded && categories.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "收起类目" : "展开类目"}
            className="absolute right-1 top-1/2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
          </button>
        )}
      </div>

      {expanded && open && categories.length > 0 && (
        <div className="mt-0.5 space-y-0.5 pl-3">
          {categories.map((c) => (
            <NavLink
              key={c.id}
              to={`${basePrefix}/artifacts/c/${c.id}`}
              title={c.name}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex h-8 items-center gap-2 rounded-lg px-2.5 text-[13px] transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )
              }
            >
              <FolderOpen className="size-4 shrink-0" />
              <span className="truncate">{c.name}</span>
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}
