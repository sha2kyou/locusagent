import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import type { ArtifactCategory } from "@/api/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { SecondarySidebar } from "@/components/SecondarySidebar";

export function ArtifactCategorySidebar({
  mobileOpen,
  onClose,
  categories,
  categoryQuery,
  onCategoryQueryChange,
  activeCategoryId,
  onSelectAll,
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
  onSelectAll: () => void;
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
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={categoryQuery}
            onChange={(e) => onCategoryQueryChange(e.target.value)}
            placeholder="搜索类目…"
            className="pl-8"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3">
        <button
          type="button"
          onClick={onSelectAll}
          className={cn(
            "mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors",
            !activeCategoryId
              ? "bg-secondary text-foreground"
              : "text-muted-foreground hover:bg-secondary/60",
          )}
        >
          <span className="min-w-0 flex-1 truncate font-medium">全部产物</span>
        </button>
        {categories === null ? (
          <div className="space-y-1.5 px-1 py-2">
            {Array.from({ length: 6 }).map((_, idx) => (
              <Skeleton key={idx} className="h-8 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            {categoryQuery ? "无匹配类目" : "暂无类目"}
          </p>
        ) : (
          filtered.map((c) => {
            const isActive = c.id === activeCategoryId;
            return (
              <div
                key={c.id}
                className={cn(
                  "group mb-1 flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors",
                  isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60",
                )}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => onSelectCategory(c)}
                >
                  <span className="block truncate font-medium">{c.name}</span>
                </button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground opacity-100 md:opacity-0 md:group-hover:opacity-100"
                  aria-label="编辑类目"
                  onClick={() => onEditCategory(c)}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground opacity-100 hover:text-destructive md:opacity-0 md:group-hover:opacity-100"
                  aria-label="删除类目"
                  onClick={() => onDeleteCategory(c)}
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
