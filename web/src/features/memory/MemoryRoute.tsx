import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Loader2, Pencil, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Button } from "@/components/ui/button";
import { Label, Textarea } from "@/components/ui/field";
import { SearchInput } from "@/components/ui/search-input";
import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { SegmentControl } from "@/components/ui/segment-control";
import { Empty, listItemDescriptionClass, listRowHoverActionsClass, Loading } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { useReloadOnAgentRecovery } from "@/hooks/useReloadOnAgentRecovery";
import { createMemory, deleteMemory, listMemory, updateMemory } from "@/api/endpoints";
import type { MemoryAnchor, MemoryEntry } from "@/api/types";
import { EMBEDDING_LABEL } from "@/lib/embedding-labels";
import { toastAction } from "@/lib/toast-copy";

export function MemoryRoute() {
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<MemoryEntry[] | null>(null);
  const [tab, setTab] = useState<MemoryAnchor>("identity");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<MemoryEntry | null>(null);
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);
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
  useReloadOnAgentRecovery(load);

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

  const resetForm = () => {
    setEditing(null);
    setContent("");
  };

  const startEdit = (m: MemoryEntry) => {
    setEditing(m);
    setContent(m.content);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const submit = async () => {
    const text = content.trim();
    if (!text) return;
    setSaving(true);
    try {
      if (editing) {
        await updateMemory(editing.id, { content: text });
        toast(toastAction("已更新", text, "记忆"), "success");
      } else {
        await createMemory({ content: text, anchor: tab });
        toast(toastAction("已添加", text, "记忆"), "success");
      }
      resetForm();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
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
    if (!(await confirm({ title: "删除记忆", body: `删除「记忆 #${m.id}」？`, danger: true, confirmText: "删除" }))) return;
    try {
      await deleteMemory(m.id);
      if (editing?.id === m.id) resetForm();
      await load();
      toast(toastAction("已删除", m.content, "记忆"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <PageContainer
      title="记忆"
      subtitle="长期与短期记忆管理"
      actions={
        items && (
          <Badge variant="outline">
            长期 {counts.identity} / 短期 {counts.experience}
          </Badge>
        )
      }
    >
      <ReadyGate>
        <div className="space-y-4">
          <SegmentControl
            value={tab}
            onChange={setTab}
            options={[
              { value: "identity", label: "长期记忆" },
              { value: "experience", label: "短期记忆" },
            ]}
          />

          <SearchInput value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索记忆…" />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty text={query ? "无匹配记忆" : "暂无记忆"} />
          ) : (
            <div className="space-y-2">
              {filtered.map((m) => {
                const emb = EMBEDDING_LABEL[m.embedding_state];
                return (
                  <ListCard key={m.id} className="group p-0 overflow-hidden">
                    <div className="flex items-start justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">记忆 #{m.id}</span>
                          <Badge variant={emb.variant}>{emb.text}</Badge>
                          {m.origin === "auto_extract" && (
                            <Badge variant="outline">自动提取</Badge>
                          )}
                        </div>
                        <p className={`${listItemDescriptionClass} max-w-[56ch] whitespace-pre-wrap`}>
                          {m.content}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => move(m)} aria-label="切换分类">
                          {m.anchor === "identity" ? <ArrowDown /> : <ArrowUp />}
                        </Button>
                        <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => startEdit(m)} aria-label="编辑">
                          <Pencil />
                        </Button>
                        <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => remove(m)} aria-label="删除">
                          <Trash2 />
                        </Button>
                      </div>
                    </div>
                    <CollapsibleSection summary="详情">
                      <pre className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap text-sm text-foreground">
                        {m.content}
                      </pre>
                    </CollapsibleSection>
                  </ListCard>
                );
              })}
            </div>
          )}

          <div ref={formRef}>
            <CollapsiblePanel
              summary={editing ? `编辑记忆 #${editing.id}` : "添加记忆"}
              defaultOpen={!!editing}
              onOpenChange={(open) => {
                if (!open) resetForm();
              }}
            >
              <div className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label>内容</Label>
                  <Textarea
                    rows={5}
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="输入要记住的内容…"
                  />
                </div>
                <div className="flex gap-2">
                  <Button variant="primary" disabled={saving || !content.trim()} onClick={submit}>
                    {saving && <Loader2 className="size-4 animate-spin" />}
                    {editing ? "保存" : "添加"}
                  </Button>
                </div>
              </div>
            </CollapsiblePanel>
          </div>
        </div>
      </ReadyGate>
    </PageContainer>
  );
}
