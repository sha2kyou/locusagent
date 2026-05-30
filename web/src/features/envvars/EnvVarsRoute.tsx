import { useEffect, useRef, useState } from "react";
import { Eye, EyeOff, Pencil, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { ReadyGate } from "@/components/ReadyGate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { useDialogs } from "@/components/ui/dialogs";
import { useToast } from "@/components/ui/toast";
import { createEnvVar, deleteEnvVar, listEnvVars, updateEnvVar } from "@/api/endpoints";
import type { EnvVarEntry } from "@/api/types";
import { Empty, Loading } from "@/features/skills/SkillsRoute";

const EMB_LABEL: Record<EnvVarEntry["embedding_state"], { text: string; variant: "neutral" | "success" | "warning" }> = {
  pending: { text: "排队中", variant: "warning" },
  ready: { text: "已索引", variant: "success" },
  failed: { text: "仅关键词", variant: "neutral" },
};

export function EnvVarsRoute() {
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<EnvVarEntry[] | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  const formRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    try {
      const { items } = await listEnvVars(200);
      setItems(items);
    } catch (e) {
      toast((e as Error).message, "error");
      setItems([]);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reset = () => {
    setEditingId(null);
    setName("");
    setValue("");
    setDescription("");
  };

  const maskValue = (raw: string) => {
    const n = Math.max(8, Math.min(24, raw.length));
    return "•".repeat(n);
  };

  const startEdit = (item: EnvVarEntry) => {
    setEditingId(item.id);
    setName(item.name);
    setValue(item.value);
    setDescription(item.description);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const submit = async () => {
    if (!name.trim() || !value.trim()) return;
    setBusy(true);
    try {
      if (editingId) {
        await updateEnvVar(editingId, {
          name: name.trim(),
          value: value.trim(),
          description: description.trim(),
        });
        toast("已更新", "success");
      } else {
        await createEnvVar({ name: name.trim(), value: value.trim(), description: description.trim() });
        toast("已添加", "success");
      }
      reset();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item: EnvVarEntry) => {
    if (!(await confirm({ title: "删除环境变量", body: `确定删除「${item.name}」？`, danger: true, confirmText: "删除" }))) return;
    setBusy(true);
    try {
      await deleteEnvVar(item.id);
      await load();
      toast("环境变量已删除", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer
      title="环境变量"
      subtitle="保存 KV 与描述，可用于密码等敏感配置"
      actions={items ? <Badge variant="outline">共 {items.length} 条</Badge> : undefined}
    >
      <ReadyGate>
        <div className="space-y-4">
          {items === null ? (
            <Loading />
          ) : items.length === 0 ? (
            <Empty text="暂无环境变量" />
          ) : (
            <div className="space-y-2">
              {items.map((item) => {
                const emb = EMB_LABEL[item.embedding_state];
                return (
                  <ListCard key={item.id} className="p-0 overflow-hidden">
                    <div className="flex items-start justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{item.name}</span>
                          <Badge variant={emb.variant}>{emb.text}</Badge>
                        </div>
                        {item.description ? (
                          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.description}</p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Button variant="ghost" size="icon-sm" onClick={() => startEdit(item)} aria-label="编辑"><Pencil /></Button>
                        <Button variant="ghost" size="icon-sm" onClick={() => remove(item)} aria-label="删除"><Trash2 /></Button>
                      </div>
                    </div>
                    <CollapsibleSection summary="值与描述">
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <p className="min-w-0 break-all text-sm text-foreground">
                            {revealed[item.id] ? item.value : maskValue(item.value)}
                          </p>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setRevealed((s) => ({ ...s, [item.id]: !s[item.id] }))}
                            aria-label={revealed[item.id] ? "隐藏值" : "显示值"}
                          >
                            {revealed[item.id] ? <EyeOff /> : <Eye />}
                          </Button>
                        </div>
                        {item.description ? (
                          <p className="text-xs text-muted-foreground">{item.description}</p>
                        ) : (
                          <p className="text-xs text-muted-foreground">（无描述）</p>
                        )}
                      </div>
                    </CollapsibleSection>
                  </ListCard>
                );
              })}
            </div>
          )}

          <div ref={formRef}>
            <CollapsiblePanel summary={editingId ? "编辑环境变量" : "添加环境变量"} defaultOpen={!!editingId}>
              <div className="grid gap-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="grid gap-1.5">
                    <Label>Key（唯一）</Label>
                    <Input value={name} disabled={!!editingId} onChange={(e) => setName(e.target.value)} placeholder="DB_PASSWORD" />
                  </div>
                  <div className="grid gap-1.5">
                    <Label>Value</Label>
                    <Input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="p@ssw0rd" />
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <Label>描述（可选）</Label>
                  <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="生产库密码" />
                </div>
                <div className="flex gap-2">
                  <Button variant="primary" onClick={submit} disabled={busy || !name.trim() || !value.trim()}>
                    {editingId ? "保存" : "添加"}
                  </Button>
                  {editingId ? <Button variant="ghost" onClick={reset}>取消编辑</Button> : null}
                </div>
              </div>
            </CollapsiblePanel>
          </div>
        </div>
      </ReadyGate>
    </PageContainer>
  );
}
