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
    <SecondarySidebar mobileOpen={mobileOpen} onClose={onClose}>
      <div className="p-3">
        <Button variant="primary" className="w-full" onClick={onAddCategory}>
          <Plus className="size-4" /> 新建类目
        </Button>
      </div>
      <div className="px-3 pb-2">
        <SearchInput
          value={categoryQuery}
          onChange={(e) => onCategoryQueryChange(e.target.value)}
          placeholder="搜索类目…"
        />
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3">
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
                  "group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors",
                  isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60",
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
                <span className="min-w-0 flex-1 truncate text-left" title={c.name}>
                  {c.name}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground"
                  aria-label="编辑类目"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEditCategory(c);
                  }}
                >
                  <Pencil />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground hover:text-destructive"
                  aria-label="删除类目"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteCategory(c);
                  }}
                >
                  <Trash2 />
                </Button>
              </div>
            );
          })
        )}
      </div>
    </SecondarySidebar>
  );
}
