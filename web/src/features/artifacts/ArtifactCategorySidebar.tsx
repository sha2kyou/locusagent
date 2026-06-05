import { Pencil, Plus, Trash2 } from "lucide-react";
import type { ArtifactCategory } from "@/api/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/ui/search-input";
import { SidebarEmpty } from "@/components/ui/list-state";
import { Skeleton } from "@/components/ui/skeleton";
import { SecondarySidebar } from "@/components/SecondarySidebar";

export function ArtifactCategorySidebar({
  mobileOpen,
  onClose,
  categories,
  categoryQuery,
  onCategoryQueryChange,
  activeCategoryId,
  onSelectCategory,
  onAddCategory,
  onEditCategory,
  onDeleteCategory,
}: {
  mobileOpen: boolean;
  onClose: () => void;
  categories: ArtifactCategory[] | null;
  categoryQuery: string;
  onCategoryQueryChange: (value: string) => void;
  activeCategoryId?: string;
  onSelectCategory: (category: ArtifactCategory) => void;
  onAddCategory: () => void;
  onEditCategory: (category: ArtifactCategory) => void;
  onDeleteCategory: (category: ArtifactCategory) => void;
}) {
  const q = categoryQuery.trim().toLowerCase();
  const filtered =
    categories?.filter((c) =>
      q ? c.name.toLowerCase().includes(q) || (c.description || "").toLowerCase().includes(q) : true,
    ) ?? [];

  return (
    <SecondarySidebar mobileOpen={mobileOpen} mobileSide="right" onClose={onClose}>
      <div className="shrink-0 space-y-2.5 border-b border-sidebar-sub-border/45 px-3 pb-3 pt-1">
        <div className="flex h-11 items-center gap-2 px-1">
          <span className="min-w-0 flex-1 text-[14px] font-bold tracking-tight">产物</span>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onAddCategory}
            title="新建类目"
            aria-label="新建类目"
          >
            <Plus className="size-4" />
          </Button>
        </div>
        <SearchInput
          value={categoryQuery}
          onChange={(e) => onCategoryQueryChange(e.target.value)}
          placeholder="搜索类目…"
        />
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3 pt-2">
        {categories === null ? (
          <div className="space-y-1.5 px-1 py-2">
            {Array.from({ length: 6 }).map((_, idx) => (
              <Skeleton key={idx} className="h-8 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <SidebarEmpty text={categoryQuery ? "无匹配类目" : "暂无类目"} />
        ) : (
          filtered.map((c) => {
            const isActive = c.id === activeCategoryId;
            return (
              <div
                key={c.id}
                className={cn(
                  "group relative flex items-center gap-1 rounded-lg px-2.5 py-2 text-[13px] transition-colors",
                  isActive
                    ? "bg-sidebar-sub-accent font-medium text-foreground shadow-xs"
                    : "text-muted-foreground hover:bg-sidebar-sub-accent/70 hover:text-foreground/90",
                )}
                role="button"
                tabIndex={0}
                onClick={() => onSelectCategory(c)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter" && e.key !== " ") return;
                  e.preventDefault();
                  onSelectCategory(c);
                }}
              >
                <span className="min-w-0 flex-1 truncate text-left leading-snug" title={c.name}>
                  {c.name}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                  aria-label="编辑类目"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEditCategory(c);
                  }}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                  aria-label="删除类目"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteCategory(c);
                  }}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            );
          })
        )}
      </div>
    </SecondarySidebar>
  );
}
