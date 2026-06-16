import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Pencil, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/field";
import { SearchInput } from "@/components/ui/search-input";
import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { SegmentControl } from "@/components/ui/segment-control";
import { Empty, listItemDescriptionClass, listRowHoverActionsClass, Loading } from "@/components/ui/list-state";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { createSkill, deleteSkill, listSkills, updateSkill } from "@/api/endpoints";
import type { Skill } from "@/api/types";
import { toastAction } from "@/lib/toast-copy";

export function SkillsRoute() {
  const { t } = useTranslation();
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<Skill[] | null>(null);
  const [tab, setTab] = useState<Skill["source"]>("private");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Skill | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [triggers, setTriggers] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    try {
      const { items } = await listSkills();
      setItems(items);
    } catch (e) {
      toast((e as Error).message, "error");
      setItems([]);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const counts = useMemo(() => {
    const list = items ?? [];
    return {
      public: list.filter((s) => s.source === "public").length,
      private: list.filter((s) => s.source === "private").length,
    };
  }, [items]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? [])
      .filter((s) => s.source === tab)
      .filter((s) =>
        q
          ? s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q) || s.body.toLowerCase().includes(q)
          : true,
      );
  }, [items, tab, query]);

  const resetForm = () => {
    setEditing(null);
    setName("");
    setDesc("");
    setTriggers("");
    setBody("");
  };

  const startEdit = (s: Skill) => {
    setEditing(s);
    setName(s.name);
    setDesc(s.description);
    setTriggers(s.triggers.join(", "));
    setBody(s.body);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const submit = async () => {
    setSaving(true);
    const triggerList = triggers
      .split(/[,，\n]/)
      .map((t) => t.trim())
      .filter(Boolean);
    try {
      if (editing) {
        await updateSkill(editing.name, { description: desc, body, triggers: triggerList });
        toast(toastAction("updated", editing.name, "skill"), "success");
      } else {
        await createSkill({ name, description: desc, body, triggers: triggerList });
        toast(toastAction("added", name, "skill"), "success");
      }
      resetForm();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (s: Skill) => {
    if (
      !(await confirm({
        title: t("skills.form.deleteTitle"),
        body: t("skills.form.deleteBody", { name: s.name }),
        danger: true,
        confirmText: t("common.actions.delete"),
      }))
    ) {
      return;
    }
    try {
      await deleteSkill(s.name);
      if (editing?.name === s.name) resetForm();
      await load();
      toast(toastAction("deleted", s.name, "skill"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <PageContainer
      title={t("skills.title")}
      subtitle={t("skills.subtitle")}
      actions={
        items && (
          <Badge variant="outline">
            {t("skills.counts.shared", { count: counts.public })} / {t("skills.counts.private", { count: counts.private })}
          </Badge>
        )
      }
    >
      <ReadyGate>
        <div className="space-y-4">
          <SegmentControl
            value={tab}
            onChange={(value) => {
              setTab(value);
              if (value === "public" && editing) resetForm();
            }}
            options={[
              { value: "public", label: t("skills.tabs.shared") },
              { value: "private", label: t("skills.tabs.private") },
            ]}
          />

          <SearchInput value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("skills.searchPlaceholder")} />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty text={query ? t("skills.noMatch") : t("skills.empty")} />
          ) : (
            <div className="space-y-2">
              {filtered.map((s) => (
                <ListCard key={`${s.source}-${s.name}`} className="group p-0 overflow-hidden">
                  <div className="flex items-start justify-between gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{s.name}</span>
                        {s.origin === "auto_extract" && (
                          <Badge variant="outline">{t("skills.badge.autoExtract")}</Badge>
                        )}
                      </div>
                      {s.description && <p className={listItemDescriptionClass}>{s.description}</p>}
                      {s.triggers.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {s.triggers.map((t) => (
                            <Tag key={t}>{t}</Tag>
                          ))}
                        </div>
                      )}
                    </div>
                    {s.source === "private" && (
                      <div className="flex shrink-0 gap-1">
                        <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => startEdit(s)} aria-label={t("common.actions.edit")}><Pencil /></Button>
                        <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => remove(s)} aria-label={t("common.actions.delete")}><Trash2 /></Button>
                      </div>
                    )}
                  </div>
                  <CollapsibleSection summary={t("common.actions.body")}>
                    <pre className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap text-sm text-foreground">
                      {s.body || t("skills.badge.noBody")}
                    </pre>
                  </CollapsibleSection>
                </ListCard>
              ))}
            </div>
          )}

          {tab === "private" && (
            <div ref={formRef}>
              <CollapsiblePanel
                summary={editing ? t("skills.form.editSummary", { name: editing.name }) : t("skills.form.addTitle")}
                defaultOpen={!!editing}
                onOpenChange={(open) => {
                  if (!open) resetForm();
                }}
              >
                <div className="grid gap-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="grid gap-1.5">
                      <Label>{t("skills.fields.name")}</Label>
                      <Input value={name} disabled={!!editing} onChange={(e) => setName(e.target.value)} placeholder="skill-name" />
                    </div>
                    <div className="grid gap-1.5">
                      <Label>{t("skills.fields.description")}</Label>
                      <Input value={desc} onChange={(e) => setDesc(e.target.value)} />
                    </div>
                  </div>
                  <div className="grid gap-1.5">
                    <Label>{t("skills.fields.triggers")}</Label>
                    <Input value={triggers} onChange={(e) => setTriggers(e.target.value)} />
                  </div>
                  <div className="grid gap-1.5">
                    <Label>{t("skills.fields.body")}</Label>
                    <Textarea rows={5} value={body} onChange={(e) => setBody(e.target.value)} />
                  </div>
                  <div className="flex gap-2">
                    <Button variant="primary" disabled={saving || !name.trim()} onClick={submit}>
                      {saving && <Loader2 className="size-4 animate-spin" />}
                      {editing ? t("common.actions.save") : t("common.actions.add")}
                    </Button>
                  </div>
                </div>
              </CollapsiblePanel>
            </div>
          )}
        </div>
      </ReadyGate>
    </PageContainer>
  );
}
