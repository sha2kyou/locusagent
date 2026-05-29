import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Check, Pencil, Trash2, X } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { ListCard } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { Empty, Loading } from "@/features/skills/SkillsRoute";
import { createMemory, deleteMemory, listMemory, updateMemory } from "@/api/endpoints";
import type { MemoryAnchor, MemoryEntry } from "@/api/types";
import { cn } from "@/lib/utils";

const TABS: { anchor: MemoryAnchor; label: string }[] = [
  { anchor: "identity", label: "常驻记忆" },
  { anchor: "experience", label: "按需检索" },
];

const EMB_LABEL: Record<MemoryEntry["embedding_state"], { text: string; variant: "neutral" | "success" | "warning" }> = {
  pending: { text: "排队中", variant: "warning" },
  ready: { text: "已索引", variant: "success" },
  failed: { text: "仅关键词", variant: "neutral" },
};

export function MemoryRoute() {
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<MemoryEntry[] | null>(null);
  const [tab, setTab] = useState<MemoryAnchor>("identity");
  const [query, setQuery] = useState("");
  const [content, setContent] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const pollRef = useRef<number | null>(null);

  const load = async (silent = false) => {
    try {
      const { items } = await listMemory(100);
      setItems(items);
    } catch (e) {
      if (!silent) toast((e as Error).message, "error");
      if (!silent) setItems([]);
    }
  };
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // embedding pending 时静默轮询
  useEffect(() => {
    const hasPending = (items ?? []).some((m) => m.embedding_state === "pending");
    if (hasPending && !pollRef.current) {
      pollRef.current = window.setInterval(() => void load(true), 3000);
    } else if (!hasPending && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [items]);

  const counts = useMemo(() => {
    const list = items ?? [];
    return {
      identity: list.filter((m) => m.anchor === "identity").length,
      experience: list.filter((m) => m.anchor === "experience").length,
    };
  }, [items]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? [])
      .filter((m) => m.anchor === tab)
      .filter((m) => (q ? m.content.toLowerCase().includes(q) : true));
  }, [items, tab, query]);

  const add = async () => {
    if (!content.trim()) return;
    try {
      await createMemory({ content: content.trim(), anchor: tab });
      setContent("");
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const saveEdit = async (id: number) => {
    try {
      await updateMemory(id, { content: editingText });
      setEditingId(null);
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const move = async (m: MemoryEntry) => {
    const next: MemoryAnchor = m.anchor === "identity" ? "experience" : "identity";
    try {
      await updateMemory(m.id, { anchor: next });
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const remove = async (m: MemoryEntry) => {
    if (!(await confirm({ title: "删除记忆", body: "确定删除该条记忆？", danger: true, confirmText: "删除" }))) return;
    try {
      await deleteMemory(m.id);
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <PageContainer title="记忆" subtitle="长期记忆条目管理">
      <ReadyGate>
        <div className="space-y-4">
          <div className="inline-flex rounded-lg border border-border bg-surface/40 p-1">
            {TABS.map((t) => (
              <button
                key={t.anchor}
                type="button"
                onClick={() => setTab(t.anchor)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  tab === t.anchor ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t.label} <span className="opacity-60">{counts[t.anchor]}</span>
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <Input
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder={tab === "identity" ? "添加到「常驻记忆」…" : "添加到「按需检索」…"}
            />
            <Button variant="primary" onClick={add} disabled={!content.trim()}>添加</Button>
          </div>

          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索记忆…" />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty text={query ? "无匹配记忆" : "暂无记忆"} />
          ) : (
            <div className="space-y-2">
              {filtered.map((m) => {
                const emb = EMB_LABEL[m.embedding_state];
                return (
                  <ListCard key={m.id}>
                    <div className="flex items-start justify-between gap-3">
                      {editingId === m.id ? (
                        <Input
                          autoFocus
                          value={editingText}
                          onChange={(e) => setEditingText(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && saveEdit(m.id)}
                        />
                      ) : (
                        <p className="min-w-0 flex-1 text-sm">{m.content}</p>
                      )}
                      <div className="flex shrink-0 items-center gap-1">
                        {editingId === m.id ? (
                          <>
                            <Button variant="ghost" size="icon-sm" onClick={() => saveEdit(m.id)} aria-label="保存"><Check /></Button>
                            <Button variant="ghost" size="icon-sm" onClick={() => setEditingId(null)} aria-label="取消"><X /></Button>
                          </>
                        ) : (
                          <>
                            <Badge variant={emb.variant}>{emb.text}</Badge>
                            <Button variant="ghost" size="icon-sm" onClick={() => move(m)} aria-label="切换分类">
                              {m.anchor === "identity" ? <ArrowDown /> : <ArrowUp />}
                            </Button>
                            <Button variant="ghost" size="icon-sm" onClick={() => { setEditingId(m.id); setEditingText(m.content); }} aria-label="编辑"><Pencil /></Button>
                            <Button variant="ghost" size="icon-sm" onClick={() => remove(m)} aria-label="删除"><Trash2 /></Button>
                          </>
                        )}
                      </div>
                    </div>
                  </ListCard>
                );
              })}
            </div>
          )}
        </div>
      </ReadyGate>
    </PageContainer>
  );
}
