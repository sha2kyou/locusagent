import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Download, Loader2, PanelLeft, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/field";
import { SearchInput } from "@/components/ui/search-input";
import { Modal } from "@/components/ui/modal";
import { Badge } from "@/components/ui/badge";
import { ListCard } from "@/components/ui/panel";
import { Drawer } from "@/components/ui/drawer";
import { Empty, listItemDescriptionClass, Loading } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { Skeleton } from "@/components/ui/skeleton";
import { formatFull, formatRelative } from "@/lib/format-time";
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
import { ArtifactCategorySidebar } from "./ArtifactCategorySidebar";

const LazyArtifactBody = lazy(() =>
  import("./ArtifactBody").then((m) => ({ default: m.ArtifactBody })),
);

const EXPORT_FORMAT: Record<ArtifactType, { ext: string; mime: string }> = {
  markdown: { ext: "md", mime: "text/markdown" },
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
  return (
    <ListCard className="p-0 overflow-hidden">
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
        <Button variant="ghost" size="icon-sm" onClick={onDelete} aria-label="删除">
          <Trash2 />
        </Button>
      </div>
    </ListCard>
  );
}

export function ArtifactsRoute() {
  const { categoryId } = useParams<{ categoryId?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { setMobileAction } = useShell();
  const toast = useToast();
  const { confirm } = useDialogs();
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

  const currentCategory = useMemo(
    () => categories?.find((c) => c.id === categoryId) ?? null,
    [categories, categoryId],
  );

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
      const { items } = await listArtifactCategories();
      setCategories(items);
    } catch (e) {
      toast((e as Error).message, "error");
      setCategories([]);
    }
  };

  const loadArtifacts = async () => {
    setItems(null);
    try {
      const { items } = await listArtifacts(categoryId);
      setItems(items);
    } catch (e) {
      toast((e as Error).message, "error");
      setItems([]);
    }
  };

  useEffect(() => {
    void loadCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadArtifacts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryId]);

  useEffect(() => {
    if (!categoryId || categories === null) return;
    if (categories.some((c) => c.id === categoryId)) return;
    navigate(toWorkspacePath("/artifacts"), { replace: true });
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

  const catName = (id: string | null) =>
    id ? ((categories ?? []).find((c) => c.id === id)?.name ?? "未分类") : "未分类";

  const filtered = useMemo(() => {
    const q = artifactQuery.trim().toLowerCase();
    return (items ?? []).filter(
      (a) => !q || a.title.toLowerCase().includes(q) || a.content.toLowerCase().includes(q),
    );
  }, [items, artifactQuery]);

  const groups = useMemo(() => {
    if (currentCategory) return [];
    const categoryList = categories ?? [];
    if (categoryList.length === 0) return [];
    const byId = new Map<string | null, ArtifactEntry[]>();
    for (const a of filtered) {
      const key = a.category_id ?? null;
      (byId.get(key) ?? byId.set(key, []).get(key)!).push(a);
    }
    const ordered: { id: string | null; name: string; items: ArtifactEntry[] }[] = [];
    for (const c of categoryList) {
      const list = byId.get(c.id);
      if (list?.length) ordered.push({ id: c.id, name: c.name, items: list });
    }
    const uncat = byId.get(null);
    if (uncat?.length) ordered.push({ id: null, name: "未分类", items: uncat });
    return ordered;
  }, [filtered, categories, currentCategory]);

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
        toast("已更新类目", "success");
      } else {
        const created = await createArtifactCategory(name, description);
        navigate(toWorkspacePath(`/artifacts/c/${created.id}`));
        toast("已添加", "success");
      }
      await loadCategories();
      await loadArtifacts();
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
        body: `删除「${c.name}」？该类目下的产物会移至未分类。`,
        danger: true,
        confirmText: "删除",
      }))
    ) {
      return;
    }
    try {
      await deleteArtifactCategory(c.id);
      await loadCategories();
      await loadArtifacts();
      if (categoryId === c.id) {
        navigate(toWorkspacePath("/artifacts"));
      }
      toast("已删除", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const removeArtifact = async (a: ArtifactEntry) => {
    if (!(await confirm({ title: "删除产物", body: `删除「${a.title}」？`, danger: true, confirmText: "删除" })))
      return;
    try {
      await deleteArtifact(a.id);
      setSelected(null);
      await loadArtifacts();
      toast("已删除", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const title = currentCategory ? currentCategory.name : "全部产物";
  const subtitle = currentCategory
    ? (currentCategory.description?.trim() || "该类目下的产物")
    : "AI 产出的成果，可按类目归档";
  const exportOriginalLabel = selected
    ? selected.type === "html"
      ? "HTML"
      : selected.type === "markdown"
        ? "Markdown"
        : "Text"
    : "原始类型";

  return (
    <>
      <div className="flex h-full">
        <ArtifactCategorySidebar
          mobileOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          categories={categories}
          categoryQuery={categoryQuery}
          onCategoryQueryChange={setCategoryQuery}
          activeCategoryId={categoryId}
          onSelectAll={() => {
            navigate(toWorkspacePath("/artifacts"));
            setSidebarOpen(false);
          }}
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
            <div className="mx-auto w-full max-w-4xl px-6 py-10">
              <header className="mb-6 space-y-1">
                <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
                <p className="text-sm text-muted-foreground">{subtitle}</p>
              </header>
              <div className="mb-4">
                <SearchInput
                  value={artifactQuery}
                  onChange={(e) => setArtifactQuery(e.target.value)}
                  placeholder="搜索产物…"
                />
              </div>

              {items === null ? (
                <Loading />
              ) : filtered.length === 0 ? (
                <Empty
                  text={
                    artifactQuery
                      ? "无匹配产物"
                      : "暂无产物，在对话中让 AI 产出成果（如「创建一条内容」）即可归档到这里"
                  }
                />
              ) : currentCategory ? (
                <div className="space-y-2">
                  {filtered.map((a) => (
                    <ArtifactRow
                      key={a.id}
                      a={a}
                      onOpen={() => setSelected(a)}
                      onDelete={() => removeArtifact(a)}
                    />
                  ))}
                </div>
              ) : (
                <div className="space-y-6">
                  {groups.map((g) => (
                    <section key={g.id ?? "_uncat"} className="space-y-2">
                      <div className="flex items-center gap-2 px-0.5">
                        <h3 className="text-sm font-semibold text-foreground">{g.name}</h3>
                        <Badge variant="outline">{g.items.length}</Badge>
                      </div>
                      {g.items.map((a) => (
                        <ArtifactRow
                          key={a.id}
                          a={a}
                          onOpen={() => setSelected(a)}
                          onDelete={() => removeArtifact(a)}
                        />
                      ))}
                    </section>
                  ))}
                </div>
              )}
            </div>
          </ReadyGate>
        </div>
      </div>

      <Modal
        open={categoryDialogOpen}
        onClose={closeCategoryDialog}
        closeDisabled={savingCategory}
        title={editingCategory ? "编辑类目" : "新建类目"}
        footer={
          <>
            <Button variant="ghost" disabled={savingCategory} onClick={closeCategoryDialog}>
              {editingCategory ? "取消编辑" : "取消"}
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
                <div className="absolute right-0 top-[calc(100%+6px)] z-20 w-48 rounded-lg border border-border bg-card p-1 shadow-lg">
                  <button
                    type="button"
                    className="block w-full rounded-md px-2.5 py-2 text-left text-sm text-foreground hover:bg-secondary"
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
