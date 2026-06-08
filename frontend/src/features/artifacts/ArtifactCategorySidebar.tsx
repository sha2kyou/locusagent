import { Pencil, Plus, Trash2 } from "lucide-react";
import type { ArtifactCategory } from "@/api/types";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/ui/search-input";
import { SidebarEmpty } from "@/components/ui/list-state";
import { Skeleton } from "@/components/ui/skeleton";
import { SecondarySidebar } from "@/components/SecondarySidebar";
import {
  SecondarySidebarHeader,
  SecondarySidebarListRow,
} from "@/components/SecondarySidebarList";
import {
  secondarySidebarListClass,
  secondarySidebarScrollClass,
  secondarySidebarSkeletonWrapClass,
} from "@/components/secondary-sidebar-styles";

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
      <SecondarySidebarHeader
        title="产物"
        actions={
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onAddCategory}
            title="新建类目"
            aria-label="新建类目"
          >
            <Plus className="size-4" />
          </Button>
        }
        search={
          <SearchInput
            value={categoryQuery}
            onChange={(e) => onCategoryQueryChange(e.target.value)}
            placeholder="搜索类目…"
          />
        }
      />

      <div className={secondarySidebarScrollClass}>
        {categories === null ? (
          <div className={secondarySidebarSkeletonWrapClass}>
            {Array.from({ length: 6 }).map((_, idx) => (
              <Skeleton key={idx} className="h-8 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <SidebarEmpty text={categoryQuery ? "无匹配类目" : "暂无类目"} />
        ) : (
          <div className={secondarySidebarListClass}>
            {filtered.map((c) => (
              <SecondarySidebarListRow
                key={c.id}
                active={c.id === activeCategoryId}
                label={c.name}
                onClick={() => onSelectCategory(c)}
                actions={
                  <>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label="编辑类目"
                      onClick={() => onEditCategory(c)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label="删除类目"
                      onClick={() => onDeleteCategory(c)}
                    >
                      <Trash2 />
                    </Button>
                  </>
                }
              />
            ))}
          </div>
        )}
      </div>
    </SecondarySidebar>
  );
}
