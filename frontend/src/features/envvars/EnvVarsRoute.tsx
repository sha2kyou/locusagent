import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Loader2, Pencil, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { ReadyGate } from "@/components/ReadyGate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { SearchInput } from "@/components/ui/search-input";
import { Empty, listItemDescriptionClass, listRowHoverActionsClass, Loading } from "@/components/ui/list-state";
import { useDialogs } from "@/components/ui/dialogs";
import { useToast } from "@/components/ui/toast";
import { createEnvVar, deleteEnvVar, listEnvVars, updateEnvVar } from "@/api/endpoints";
import type { EnvVarEntry } from "@/api/types";
import { EMBEDDING_LABEL } from "@/lib/embedding-labels";
import { toastAction } from "@/lib/toast-copy";

export function EnvVarsRoute() {
  const { t } = useTranslation();
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<EnvVarEntry[] | null>(null);
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
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
    setSaving(true);
    try {
      if (editingId) {
        await updateEnvVar(editingId, {
          name: name.trim(),
          value: value.trim(),
          description: description.trim(),
        });
        toast(toastAction("updated", name.trim(), "envVar"), "success");
      } else {
        await createEnvVar({ name: name.trim(), value: value.trim(), description: description.trim() });
        toast(toastAction("added", name.trim(), "envVar"), "success");
      }
      reset();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: EnvVarEntry) => {
    if (
      !(await confirm({
        title: t("envVars.form.deleteTitle"),
        body: t("envVars.form.deleteBody", { name: item.name }),
        danger: true,
        confirmText: t("common.actions.delete"),
      }))
    ) {
      return;
    }
    setSaving(true);
    try {
      await deleteEnvVar(item.id);
      if (editingId === item.id) reset();
      await load();
      toast(toastAction("deleted", item.name, "envVar"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = items ?? [];
    if (!q) return list;
    return list.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q),
    );
  }, [items, query]);

  return (
    <PageContainer
      title={t("envVars.title")}
      subtitle={t("envVars.subtitle")}
      actions={items ? <Badge variant="outline">{t("envVars.count", { count: items.length })}</Badge> : undefined}
    >
      <ReadyGate>
        <div className="space-y-4">
          <SearchInput
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("envVars.searchPlaceholder")}
          />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty text={query ? t("envVars.noMatch") : t("envVars.empty")} />
          ) : (
            <div className="space-y-2">
              {filtered.map((item) => {
                const emb = EMBEDDING_LABEL[item.embedding_state];
                return (
                  <ListCard key={item.id} className="group p-0 overflow-hidden">
                    <div className="flex items-start justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{item.name}</span>
                          <Badge variant={emb.variant}>{emb.text}</Badge>
                        </div>
                        {item.description ? (
                          <p className={listItemDescriptionClass}>{item.description}</p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => startEdit(item)} aria-label={t("common.actions.edit")}><Pencil /></Button>
                        <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => remove(item)} aria-label={t("common.actions.delete")}><Trash2 /></Button>
                      </div>
                    </div>
                    <CollapsibleSection summary={t("envVars.detail.valueAndDescription")}>
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <p className="min-w-0 break-all text-sm text-foreground">
                            {revealed[item.id] ? item.value : maskValue(item.value)}
                          </p>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setRevealed((s) => ({ ...s, [item.id]: !s[item.id] }))}
                            aria-label={revealed[item.id] ? t("envVars.detail.hideValue") : t("envVars.detail.showValue")}
                          >
                            {revealed[item.id] ? <EyeOff /> : <Eye />}
                          </Button>
                        </div>
                        {item.description ? (
                          <p className="text-xs text-muted-foreground">{item.description}</p>
                        ) : (
                          <p className="text-xs text-muted-foreground">{t("envVars.detail.noDescription")}</p>
                        )}
                      </div>
                    </CollapsibleSection>
                  </ListCard>
                );
              })}
            </div>
          )}

          <div ref={formRef}>
            <CollapsiblePanel
              summary={editingId ? t("envVars.form.editTitle") : t("envVars.form.addTitle")}
              defaultOpen={!!editingId}
              onOpenChange={(open) => {
                if (!open) reset();
              }}
            >
              <div className="grid gap-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="grid gap-1.5">
                    <Label>{t("envVars.fields.key")}</Label>
                    <Input value={name} disabled={!!editingId} onChange={(e) => setName(e.target.value)} placeholder="DB_PASSWORD" />
                  </div>
                  <div className="grid gap-1.5">
                    <Label>Value</Label>
                    <Input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="p@ssw0rd" />
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <Label>{t("envVars.fields.description")}</Label>
                  <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t("envVars.fields.valuePlaceholder")} />
                </div>
                <div className="flex gap-2">
                  <Button variant="primary" onClick={submit} disabled={saving || !name.trim() || !value.trim()}>
                    {saving && <Loader2 className="size-4 animate-spin" />}
                    {editingId ? t("common.actions.save") : t("common.actions.add")}
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
