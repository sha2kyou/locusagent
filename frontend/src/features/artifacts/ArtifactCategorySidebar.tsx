import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const q = categoryQuery.trim().toLowerCase();
  const filtered =
    categories?.filter((c) =>
      q ? c.name.toLowerCase().includes(q) || (c.description || "").toLowerCase().includes(q) : true,
    ) ?? [];

  return (
    <SecondarySidebar mobileOpen={mobileOpen} mobileSide="right" onClose={onClose}>
      <SecondarySidebarHeader
        title={t("artifacts.title")}
        actions={
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onAddCategory}
            title={t("nav.artifactsNewCategory")}
            aria-label={t("nav.artifactsNewCategory")}
          >
            <Plus className="size-4" />
          </Button>
        }
        search={
          <SearchInput
            value={categoryQuery}
            onChange={(e) => onCategoryQueryChange(e.target.value)}
            placeholder={t("artifacts.sidebar.searchPlaceholder")}
          />
        }
      />

      <div className={secondarySidebarScrollClass}>
        {categories === null ? (
          <div className={secondarySidebarSkeletonWrapClass}>
            {Array.from({ length: 6 }).map((_, idx) => (
              <Skeleton key={idx} className="h-7 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <SidebarEmpty text={categoryQuery ? t("artifacts.sidebar.noMatch") : t("artifacts.sidebar.empty")} />
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
                      aria-label={t("artifacts.sidebar.editCategory")}
                      onClick={() => onEditCategory(c)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("artifacts.sidebar.deleteCategory")}
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
