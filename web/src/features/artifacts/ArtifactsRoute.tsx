import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Download, Plus, Trash2 } from "lucide-react";
import { jsPDF } from "jspdf";
import { PageContainer } from "@/components/PageContainer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { ListCard } from "@/components/ui/panel";
import { Drawer } from "@/components/ui/drawer";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { Empty, Loading } from "@/features/skills/SkillsRoute";
import { HtmlRender, Markdown } from "@/features/chat/Markdown";
import {
  createArtifactCategory,
  deleteArtifact,
  deleteArtifactCategory,
  listArtifactCategories,
  listArtifacts,
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

function artifactToText(a: ArtifactEntry): string {
  if (a.type !== "html") return a.content;
  const doc = new DOMParser().parseFromString(a.content, "text/html");
  return (doc.body.textContent || "").trim();
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

function downloadArtifactPdf(a: ArtifactEntry): void {
  const safeTitle = safeFileTitle(a.title);
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const margin = 40;
  const pageWidthPt = doc.internal.pageSize.getWidth();
  const pageHeightPt = doc.internal.pageSize.getHeight();
  const scale = 2;
  const pageWidthPx = Math.round(pageWidthPt * scale);
  const pageHeightPx = Math.round(pageHeightPt * scale);
  const marginPx = Math.round(margin * scale);
  const contentWidthPx = pageWidthPx - marginPx * 2;
  const lineHeightPx = 32;
  const titleLineHeightPx = 42;
  const paragraphGapPx = 14;
  const pageMaxY = pageHeightPx - marginPx;
  const fontFamily = "PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif";

  const text = artifactToText(a) || "(empty)";
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const wrapLine = (input: string, maxWidth: number): string[] => {
    if (!input) return [""];
    const out: string[] = [];
    let current = "";
    for (const ch of input) {
      const next = current + ch;
      if (ctx.measureText(next).width <= maxWidth || current.length === 0) {
        current = next;
      } else {
        out.push(current);
        current = ch;
      }
    }
    if (current) out.push(current);
    return out;
  };

  ctx.font = `700 30px ${fontFamily}`;
  const titleLines = wrapLine(a.title || "artifact", contentWidthPx);

  ctx.font = `400 26px ${fontFamily}`;
  const bodyLines: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trimEnd();
    const wrapped = wrapLine(line, contentWidthPx);
    bodyLines.push(...wrapped);
    bodyLines.push("");
  }
  if (bodyLines.length > 0 && bodyLines[bodyLines.length - 1] === "") {
    bodyLines.pop();
  }

  const pages: { title: string[]; body: string[] }[] = [];
  let lineIndex = 0;
  let firstPage = true;
  while (lineIndex < bodyLines.length || (firstPage && bodyLines.length === 0)) {
    const titleBlock = firstPage ? titleLines : [];
    const startY = marginPx + titleBlock.length * titleLineHeightPx + (firstPage ? paragraphGapPx * 2 : 0);
    const availableBodyLines = Math.max(0, Math.floor((pageMaxY - startY) / lineHeightPx));
    const bodyBlock =
      availableBodyLines > 0 ? bodyLines.slice(lineIndex, lineIndex + availableBodyLines) : [];
    pages.push({ title: titleBlock, body: bodyBlock });
    lineIndex += bodyBlock.length;
    if (availableBodyLines === 0) break;
    firstPage = false;
  }
  if (pages.length === 0) pages.push({ title: titleLines, body: ["(empty)"] });

  pages.forEach((page, i) => {
    if (i > 0) doc.addPage();
    canvas.width = pageWidthPx;
    canvas.height = pageHeightPx;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    let y = marginPx;
    if (page.title.length > 0) {
      ctx.fillStyle = "#111111";
      ctx.font = `700 30px ${fontFamily}`;
      for (const line of page.title) {
        ctx.fillText(line || " ", marginPx, y);
        y += titleLineHeightPx;
      }
      y += paragraphGapPx;
    }

    ctx.fillStyle = "#111111";
    ctx.font = `400 26px ${fontFamily}`;
    for (const line of page.body) {
      ctx.fillText(line || " ", marginPx, y);
      y += lineHeightPx;
    }

    const imageData = canvas.toDataURL("image/jpeg", 0.92);
    doc.addImage(imageData, "JPEG", 0, 0, pageWidthPt, pageHeightPt, undefined, "FAST");
  });

  doc.save(`${safeTitle}.pdf`);
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
  const toast = useToast();
  const { confirm, prompt } = useDialogs();
  const [categories, setCategories] = useState<ArtifactCategory[]>([]);
  const [items, setItems] = useState<ArtifactEntry[] | null>(null);
  const [selected, setSelected] = useState<ArtifactEntry | null>(null);
  const [query, setQuery] = useState("");

  const currentCategory = useMemo(
    () => categories.find((c) => c.id === categoryId) ?? null,
    [categories, categoryId],
  );

  const loadCategories = async () => {
    try {
      const { items } = await listArtifactCategories();
      setCategories(items);
    } catch {
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

  const addCategory = async () => {
    const name = (
      await prompt({
        title: "新增类目",
        placeholder: "类目名（子菜单），如「广告」「报告」",
        confirmText: "新增",
      })
    )?.trim();
    if (!name) return;
    const description =
      (
        await prompt({
          title: "类目描述（可选）",
          placeholder: "例如：用于保存广告文案、投放创意与渠道素材",
          confirmText: "确定",
        })
      )?.trim() ?? "";
    try {
      await createArtifactCategory(name, description);
      await loadCategories();
      notifyCategoriesChanged();
      toast("已新增类目", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const removeCategory = async () => {
    if (!currentCategory) return;
    if (
      !(await confirm({
        title: "删除类目",
        body: `删除「${currentCategory.name}」？该类目下的产物会移至未分类。`,
        danger: true,
        confirmText: "删除",
      }))
    )
      return;
    try {
      await deleteArtifactCategory(currentCategory.id);
      notifyCategoriesChanged();
      window.location.href = "/artifacts";
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

  const title = currentCategory ? currentCategory.name : "全部产物";
  const subtitle = currentCategory ? "该类目下的产物" : "AI 产出的成果，可按类目（子菜单）归档";

  return (
    <PageContainer
      title={title}
      subtitle={subtitle}
      actions={
        currentCategory ? (
          <Button variant="ghost" size="sm" onClick={removeCategory}>
            <Trash2 className="size-4" /> 删除类目
          </Button>
        ) : (
          <Button variant="secondary" size="sm" onClick={addCategory}>
            <Plus className="size-4" /> 新增类目
          </Button>
        )
      }
    >
      <ReadyGate>
        <div className="space-y-4">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索产物…" />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty
              text={
                query
                  ? "无匹配产物"
                  : "暂无产物，在对话中让 AI 产出成果（如「创建一条广告」）即可归档到这里"
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
            <>
              <Button variant="ghost" size="sm" onClick={() => downloadArtifactOriginal(selected)} title="按原始类型导出">
                <Download className="size-4" /> 原始类型
              </Button>
              <Button variant="ghost" size="sm" onClick={() => downloadArtifactPdf(selected)} title="导出为 PDF">
                <Download className="size-4" /> PDF
              </Button>
            </>
          )
        }
      >
        {selected && <ArtifactBody artifact={selected} />}
      </Drawer>
    </PageContainer>
  );
}
