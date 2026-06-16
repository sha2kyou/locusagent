import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Download, Loader2, PanelLeft, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/field";
import { SearchInput } from "@/components/ui/search-input";
import { Modal } from "@/components/ui/modal";
import { ListCard } from "@/components/ui/panel";
import { Drawer } from "@/components/ui/drawer";
import { Empty, listItemDescriptionClass, listRowHoverActionsClass, Loading } from "@/components/ui/list-state";
import { PageContainer } from "@/components/PageContainer";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { Skeleton } from "@/components/ui/skeleton";
import { useTimeFormatters } from "@/lib/use-app-timezone";
import { toastAction } from "@/lib/toast-copy";
import {
  createArtifactCategory,
  deleteArtifact,
  deleteArtifactCategory,
  listArtifactCategories,
  listArtifacts,
  updateArtifactCategory,
} from "@/api/endpoints";
import type { ArtifactCategory, ArtifactEntry, ArtifactType } from "@/api/types";
import { useShell } from "@/app/AppShell";
import { stripWorkspacePrefix, withWorkspacePrefix } from "@/app/workspace-route";
import { defaultArtifactsPath } from "./artifact-routes";
import { ArtifactCategorySidebar } from "./ArtifactCategorySidebar";
import { floatingMenuItemClass, floatingPanelClass } from "@/components/ui/surface-styles";

const LazyArtifactBody = lazy(() =>
  import("./ArtifactBody").then((m) => ({ default: m.ArtifactBody })),
);

const EXPORT_FORMAT: Record<ArtifactType, { ext: string; mime: string }> = {
  markdown: { ext: "md", mime: "text/markdown" },
  latex: { ext: "md", mime: "text/markdown" },
  html: { ext: "html", mime: "text/html" },
  text: { ext: "txt", mime: "text/plain" },
};

function safeFileTitle(title: string): string {
  return (title || "artifact").replace(/[\\/:*?"<>|]/g, "_").trim().slice(0, 80) || "artifact";
}

function downloadArtifactOriginal(a: ArtifactEntry): void {
  const fmt = EXPORT_FORMAT[a.type] ?? EXPORT_FORMAT.text;
  const safeTitle = safeFileTitle(a.title);
  const blob = new Blob([a.content], { type: `${fmt.mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safeTitle || "artifact"}.${fmt.ext}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function excerpt(content: string): string {
  const flat = content
    .replace(/<[^>]+>/g, " ")
    .replace(/[#*`>\-_[\]]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return flat.length > 120 ? flat.slice(0, 120) + "…" : flat;
}

function ArtifactRow({
  a,
  onOpen,
  onDelete,
}: {
  a: ArtifactEntry;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const { formatRelative } = useTimeFormatters();
  return (
    <ListCard className="group p-0 overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-medium">{a.title}</span>
            <span className="shrink-0 text-sm text-muted-foreground">
              {formatRelative(a.created_at)}
            </span>
          </div>
          <p className={listItemDescriptionClass}>{excerpt(a.content)}</p>
        </button>
        <Button
          variant="ghost"
          size="icon-sm"
          className={listRowHoverActionsClass}
          onClick={onDelete}
          aria-label="删除"
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
    </ListCard>
  );
}

export function ArtifactsRoute() {
  const { categoryId } = useParams<{ categoryId?: string }>();
  return <ArtifactsPage categoryId={categoryId} />;
}

function ArtifactsPage({ categoryId }: { categoryId?: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { setMobileAction } = useShell();
  const toast = useToast();
  const { confirm } = useDialogs();
  const { formatFull } = useTimeFormatters();
  const [categories, setCategories] = useState<ArtifactCategory[] | null>(null);
  const [items, setItems] = useState<ArtifactEntry[] | null>(null);
  const [selected, setSelected] = useState<ArtifactEntry | null>(null);
  const [artifactQuery, setArtifactQuery] = useState("");
  const [categoryQuery, setCategoryQuery] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<ArtifactCategory | null>(null);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [newCategoryDesc, setNewCategoryDesc] = useState("");
  const [savingCategory, setSavingCategory] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const routeWorkspace = stripWorkspacePrefix(location.pathname);
  const toWorkspacePath = (path: string) => withWorkspacePrefix(path, routeWorkspace.workspaceId);

  const showCategoryView = Boolean(categoryId);

  const currentCategory = useMemo(
    () =>
      showCategoryView ? (categories?.find((c) => c.id === categoryId) ?? null) : null,
    [categories, categoryId, showCategoryView],
  );

  const navigateAfterCategoriesChange = (cats: ArtifactCategory[]) => {
    const path = defaultArtifactsPath(cats, routeWorkspace.workspaceId);
    navigate(path ?? withWorkspacePrefix("/artifacts", routeWorkspace.workspaceId), { replace: true });
  };

  useEffect(() => {
    setMobileAction(
      <button
        type="button"
        onClick={() => setSidebarOpen(true)}
        aria-label="产物类目"
        className="inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        <PanelLeft className="size-5" />
      </button>,
    );
    return () => setMobileAction(null);
  }, [setMobileAction]);

  const loadCategories = async () => {
    try {
      const { items: cats } = await listArtifactCategories();
      setCategories(cats);
      return cats;
    } catch (e) {
      toast((e as Error).message, "error");
      setCategories([]);
      return [];
    }
  };

  const loadArtifacts = async () => {
    if (!categoryId) return;
    setItems(null);
    try {
      const { items: scoped } = await listArtifacts(categoryId);
      setItems(scoped);
    } catch (e) {
      toast((e as Error).message, "error");
      setItems([]);
    }
  };

  useEffect(() => {
    void loadCategories();
    if (!categoryId) {
      setItems([]);
      return;
    }
    void loadArtifacts();
  }, [categoryId]);

  useEffect(() => {
    if (!categoryId) {
      setItems([]);
      return;
    }
    void loadArtifacts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryId]);

  useEffect(() => {
    if (categories === null) return;
    if (!categoryId && categories.length > 0) {
      const path = defaultArtifactsPath(categories, routeWorkspace.workspaceId);
      if (path) navigate(path, { replace: true });
      return;
    }
    if (!categoryId) return;
    if (categories.some((c) => c.id === categoryId)) return;
    navigateAfterCategoriesChange(categories);
  }, [categories, categoryId, navigate, routeWorkspace.workspaceId]);

  useEffect(() => {
    if (!exportMenuOpen) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (exportMenuRef.current?.contains(target)) return;
      setExportMenuOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [exportMenuOpen]);

  const filtered = useMemo(() => {
    const q = artifactQuery.trim().toLowerCase();
    const list = (items ?? []).filter(
      (a) => !q || a.title.toLowerCase().includes(q) || a.content.toLowerCase().includes(q),
    );
    return list.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
  }, [items, artifactQuery]);

  const closeCategoryDialog = () => {
    setCategoryDialogOpen(false);
    setEditingCategory(null);
    setNewCategoryName("");
    setNewCategoryDesc("");
  };

  const addCategory = () => {
    setEditingCategory(null);
    setNewCategoryName("");
    setNewCategoryDesc("");
    setCategoryDialogOpen(true);
  };

  const submitCategory = async () => {
    const name = newCategoryName.trim();
    if (!name) return;
    const description = newCategoryDesc.trim();
    setSavingCategory(true);
    try {
      if (editingCategory) {
        await updateArtifactCategory(editingCategory.id, { name, description });
        toast(toastAction("已更新", name, "类目"), "success");
      } else {
        const created = await createArtifactCategory(name, description);
        navigate(toWorkspacePath(`/artifacts/c/${created.id}`));
        toast(toastAction("已添加", name, "类目"), "success");
      }
      await loadCategories();
      if (categoryId) await loadArtifacts();
      closeCategoryDialog();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSavingCategory(false);
    }
  };

  const startEditCategory = (c: ArtifactCategory) => {
    setEditingCategory(c);
    setNewCategoryName(c.name);
    setNewCategoryDesc(c.description || "");
    setCategoryDialogOpen(true);
  };

  const removeCategoryById = async (c: ArtifactCategory) => {
    if (
      !(await confirm({
        title: "删除类目",
        body: `删除「${c.name}」？该类目下的产物将一并删除。`,
        danger: true,
        confirmText: "删除",
      }))
    ) {
      return;
    }
    try {
      await deleteArtifactCategory(c.id);
      const cats = await loadCategories();
      await loadArtifacts();
      if (categoryId === c.id) {
        navigateAfterCategoriesChange(cats);
      }
      toast(toastAction("已删除", c.name, "类目"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const removeArtifact = async (a: ArtifactEntry) => {
    if (
      !(await confirm({
        title: "删除产物",
        body: `确定删除「${a.title}」？此操作不可恢复。`,
        danger: true,
        confirmText: "删除",
      }))
    )
      return;
    try {
      await deleteArtifact(a.id);
      setSelected(null);
      await loadArtifacts();
      toast(toastAction("已删除", a.title, "产物"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const title = showCategoryView ? (currentCategory?.name ?? "产物") : "产物";
  const subtitle = showCategoryView
    ? currentCategory?.description?.trim() || "该类目下的产物，按保存时间从新到旧显示"
    : "创建类目后，可在此查看归档产物";
  const exportOriginalLabel = selected
    ? selected.type === "html"
      ? "HTML"
      : selected.type === "latex"
        ? "LaTeX"
        : selected.type === "markdown"
          ? "Markdown"
          : "Text"
    : "原始类型";

  const catName = (id: string | null) =>
    id ? ((categories ?? []).find((c) => c.id === id)?.name ?? "") : "";

  return (
    <>
      <div className="flex h-full">
        <ArtifactCategorySidebar
          mobileOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          categories={categories}
          categoryQuery={categoryQuery}
          onCategoryQueryChange={setCategoryQuery}
          activeCategoryId={showCategoryView ? categoryId : undefined}
          onSelectCategory={(c) => {
            navigate(toWorkspacePath(`/artifacts/c/${c.id}`));
            setSidebarOpen(false);
          }}
          onAddCategory={addCategory}
          onEditCategory={startEditCategory}
          onDeleteCategory={(c) => {
            void removeCategoryById(c);
          }}
        />

        <div className="min-w-0 flex-1 overflow-y-auto">
          <ReadyGate>
            {categories === null ? (
              <PageContainer embedded title="产物" subtitle="创建类目后，可在此查看归档产物">
                <Loading />
              </PageContainer>
            ) : !showCategoryView ? (
              <PageContainer embedded title={title} subtitle={subtitle}>
                <Empty text="暂无类目。点击侧栏「新建类目」创建第一个类目。" />
              </PageContainer>
            ) : currentCategory === null ? (
              <PageContainer embedded title={title} subtitle={subtitle}>
                <Loading />
              </PageContainer>
            ) : (
              <PageContainer embedded title={title} subtitle={subtitle}>
                <div className="space-y-4">
                  <SearchInput
                    value={artifactQuery}
                    onChange={(e) => setArtifactQuery(e.target.value)}
                    placeholder="搜索产物…"
                  />

                  {items === null ? (
                    <Loading />
                  ) : filtered.length === 0 ? (
                    <Empty
                      text={
                        artifactQuery
                          ? "无匹配产物"
                          : "暂无产物。在对话中请 AI 保存、导出或归档内容后，会出现在这里"
                      }
                    />
                  ) : (
                    <div className="space-y-2">
                      {filtered.map((a) => (
                        <ArtifactRow
                          key={a.id}
                          a={a}
                          onOpen={() => setSelected(a)}
                          onDelete={() => {
                            void removeArtifact(a);
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </PageContainer>
            )}
          </ReadyGate>
        </div>
      </div>

      <Modal
        open={categoryDialogOpen}
        onClose={closeCategoryDialog}
        closeDisabled={savingCategory}
        title={editingCategory ? "编辑类目" : "新建类目"}
        description="名称用于展示，描述可帮助 AI 在归档时选择合适类目。"
        size="sm"
        footer={
          <>
            <Button variant="secondary" disabled={savingCategory} onClick={closeCategoryDialog}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={savingCategory || !newCategoryName.trim()}
              onClick={() => {
                void submitCategory();
              }}
            >
              {savingCategory && <Loader2 className="size-4 animate-spin" />}
              {editingCategory ? "保存" : "添加"}
            </Button>
          </>
        }
      >
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label>类目名称</Label>
            <Input
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              placeholder="如：内容、报告、规划"
            />
          </div>
          <div className="grid gap-1.5">
            <Label>类目描述（可选）</Label>
            <Textarea
              rows={3}
              value={newCategoryDesc}
              onChange={(e) => setNewCategoryDesc(e.target.value)}
              placeholder="用于指导 AI 选择该类目"
            />
          </div>
        </div>
      </Modal>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.title}
        description={
          selected
            ? `${catName(selected.category_id)} · ${formatFull(selected.created_at)}`
            : undefined
        }
        actions={
          selected && (
            <div ref={exportMenuRef} className="relative">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setExportMenuOpen((v) => !v)}
                title="导出"
                aria-label="导出"
                aria-haspopup="menu"
                aria-expanded={exportMenuOpen}
              >
                <Download className="size-4" />
              </Button>
              {exportMenuOpen && (
                <div className={cn("absolute right-0 top-[calc(100%+6px)] z-20 w-44 py-1", floatingPanelClass)}>
                  <button
                    type="button"
                    className={floatingMenuItemClass}
                    onClick={() => {
                      downloadArtifactOriginal(selected);
                      setExportMenuOpen(false);
                    }}
                  >
                    {exportOriginalLabel}
                  </button>
                </div>
              )}
            </div>
          )
        }
      >
        <div>
          {selected && (
            <Suspense
              fallback={
                <div className="space-y-2 py-2">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                </div>
              }
            >
              <LazyArtifactBody artifact={selected} />
            </Suspense>
          )}
        </div>
      </Drawer>
    </>
  );
}
