import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { Download, Pencil, Plus, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { Drawer } from "@/components/ui/drawer";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { Empty, Loading } from "@/features/skills/SkillsRoute";
import { HtmlRender, Markdown } from "@/features/chat/Markdown";
import { cn } from "@/lib/utils";
import {
  createArtifactCategory,
  deleteArtifact,
  deleteArtifactCategory,
  listArtifactCategories,
  listArtifacts,
  updateArtifactCategory,
} from "@/api/endpoints";
import type { ArtifactCategory, ArtifactEntry, ArtifactType } from "@/api/types";

const CATEGORIES_CHANGED = "artifacts:categories-changed";

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

function notifyCategoriesChanged() {
  window.dispatchEvent(new Event(CATEGORIES_CHANGED));
}

function formatRelative(iso: string): string {
  const t = new Date(iso.includes("Z") || iso.includes("+") ? iso : iso + "Z").getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return new Date(t).toLocaleDateString();
}

function formatFull(iso: string): string {
  const t = new Date(iso.includes("Z") || iso.includes("+") ? iso : iso + "Z").getTime();
  if (Number.isNaN(t)) return iso;
  return new Date(t).toLocaleString();
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
    <ListCard>
      <div className="flex items-start gap-2">
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-medium">{a.title}</span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {formatRelative(a.created_at)}
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{excerpt(a.content)}</p>
        </button>
        <Button variant="ghost" size="icon-sm" onClick={onDelete} aria-label="删除">
          <Trash2 />
        </Button>
      </div>
    </ListCard>
  );
}

function ArtifactBody({ artifact }: { artifact: ArtifactEntry }) {
  if (artifact.type === "html") return <HtmlRender html={artifact.content} />;
  if (artifact.type === "text")
    return (
      <pre className="whitespace-pre-wrap wrap-break-word font-mono text-[13px] leading-relaxed">
        {artifact.content}
      </pre>
    );
  return <Markdown text={artifact.content} />;
}

export function ArtifactsRoute() {
  const { categoryId } = useParams<{ categoryId?: string }>();
  const location = useLocation();
  const toast = useToast();
  const { confirm } = useDialogs();
  const [categories, setCategories] = useState<ArtifactCategory[]>([]);
  const [items, setItems] = useState<ArtifactEntry[] | null>(null);
  const [selected, setSelected] = useState<ArtifactEntry | null>(null);
  const [query, setQuery] = useState("");
  const [addCategoryOpen, setAddCategoryOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<ArtifactCategory | null>(null);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [newCategoryDesc, setNewCategoryDesc] = useState("");
  const addCategoryRef = useRef<HTMLDivElement>(null);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);

  const currentCategory = useMemo(
    () => categories.find((c) => c.id === categoryId) ?? null,
    [categories, categoryId],
  );
  const manageMode = location.pathname === "/artifacts/manage" && !currentCategory;

  const loadCategories = async () => {
    try {
      const { items } = await listArtifactCategories();
      setCategories(items);
    } catch {
      setCategories([]);
    }
  };

  const loadArtifacts = async () => {
    if (manageMode) {
      setItems([]);
      return;
    }
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
  }, [categoryId, manageMode]);

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
    id ? (categories.find((c) => c.id === id)?.name ?? "未分类") : "未分类";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter(
      (a) => !q || a.title.toLowerCase().includes(q) || a.content.toLowerCase().includes(q),
    );
  }, [items, query]);

  const groups = useMemo(() => {
    if (currentCategory) return [];
    const byId = new Map<string | null, ArtifactEntry[]>();
    for (const a of filtered) {
      const key = a.category_id ?? null;
      (byId.get(key) ?? byId.set(key, []).get(key)!).push(a);
    }
    const ordered: { id: string | null; name: string; items: ArtifactEntry[] }[] = [];
    for (const c of categories) {
      const list = byId.get(c.id);
      if (list?.length) ordered.push({ id: c.id, name: c.name, items: list });
    }
    const uncat = byId.get(null);
    if (uncat?.length) ordered.push({ id: null, name: "未分类", items: uncat });
    return ordered;
  }, [filtered, categories, currentCategory]);
  const filteredCategories = useMemo(() => {
    const q = query.trim().toLowerCase();
    return categories.filter((c) =>
      q ? c.name.toLowerCase().includes(q) || (c.description || "").toLowerCase().includes(q) : true,
    );
  }, [categories, query]);
  const isDescriptionExpandable = (text: string) => {
    const lines = text.split(/\r?\n/).length;
    return lines > 2 || text.length > 140;
  };

  const addCategory = () => {
    setEditingCategory(null);
    setAddCategoryOpen(true);
    requestAnimationFrame(() => addCategoryRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const submitAddCategory = async () => {
    const name = newCategoryName.trim();
    if (!name) return;
    const description = newCategoryDesc.trim();
    try {
      if (editingCategory) {
        await updateArtifactCategory(editingCategory.id, { name, description });
        toast("已更新类目", "success");
      } else {
        await createArtifactCategory(name, description);
        toast("已新增类目", "success");
      }
      await loadCategories();
      notifyCategoriesChanged();
      setNewCategoryName("");
      setNewCategoryDesc("");
      setAddCategoryOpen(false);
      setEditingCategory(null);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const startEditCategory = (c: ArtifactCategory) => {
    setEditingCategory(c);
    setNewCategoryName(c.name);
    setNewCategoryDesc(c.description || "");
    setAddCategoryOpen(true);
    requestAnimationFrame(() => addCategoryRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
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
      notifyCategoriesChanged();
      await loadCategories();
      toast("已删除类目", "success");
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
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const title = currentCategory ? currentCategory.name : manageMode ? "产物类目管理" : "全部产物";
  const subtitle = currentCategory
    ? (currentCategory.description?.trim() || "该类目下的产物")
    : manageMode
      ? "管理产物类目与描述"
      : "AI 产出的成果，可按类目（子菜单）归档";
  const exportOriginalLabel = selected
    ? selected.type === "html"
      ? "HTML"
      : selected.type === "markdown"
        ? "Markdown"
        : "Text"
    : "原始类型";

  return (
    <PageContainer
      title={title}
      subtitle={subtitle}
      actions={
        !currentCategory && !manageMode ? (
          <Button variant="secondary" size="sm" onClick={addCategory}>
            <Plus className="size-4" /> 新增类目
          </Button>
        ) : undefined
      }
    >
      <ReadyGate>
        <div className="space-y-4">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索产物…" />

          {items === null ? (
            <Loading />
          ) : manageMode ? (
            filteredCategories.length === 0 ? (
              <Empty text={query ? "无匹配类目" : "暂无类目，先新增一个类目"} />
            ) : (
              <div className="space-y-2">
                {filteredCategories.map((c) => {
                  const desc = (c.description || "").trim();
                  const expandable = !!desc && isDescriptionExpandable(desc);
                  return (
                    <ListCard key={c.id} className="p-0 overflow-hidden">
                      <div className="flex items-start justify-between gap-3 px-4 py-3">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-foreground">{c.name}</div>
                          {desc ? (
                            <div
                              className={cn(
                                "mt-1 whitespace-pre-wrap text-sm text-muted-foreground",
                                expandable && "line-clamp-2",
                              )}
                            >
                              {desc}
                            </div>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => startEditCategory(c)}
                            aria-label="编辑类目"
                          >
                            <Pencil className="size-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => {
                              void removeCategoryById(c);
                            }}
                            aria-label="删除类目"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      </div>
                      {desc ? (
                        <CollapsibleSection summary="展开更多">
                          <pre className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap text-sm text-foreground">
                            {desc}
                          </pre>
                        </CollapsibleSection>
                      ) : null}
                    </ListCard>
                  );
                })}
              </div>
            )
          ) : filtered.length === 0 ? (
            <Empty
              text={
                query
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

          {!currentCategory ? (
            <div ref={addCategoryRef}>
              <CollapsiblePanel summary={editingCategory ? "编辑类目" : "新增类目"} defaultOpen={addCategoryOpen}>
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
                      placeholder="用于指导 AI 选择该类目，例如：保存发布资料与内容文案"
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="primary"
                      disabled={!newCategoryName.trim()}
                      onClick={() => {
                        void submitAddCategory();
                      }}
                    >
                      {editingCategory ? "保存" : "新增"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setEditingCategory(null);
                        setAddCategoryOpen(false);
                        setNewCategoryName("");
                        setNewCategoryDesc("");
                      }}
                    >
                      取消
                    </Button>
                  </div>
                </div>
              </CollapsiblePanel>
            </div>
          ) : null}
        </div>
      </ReadyGate>

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
        <div>{selected && <ArtifactBody artifact={selected} />}</div>
      </Drawer>

    </PageContainer>
  );
}
