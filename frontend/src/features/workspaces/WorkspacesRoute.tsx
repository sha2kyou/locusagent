import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, Loader2, Pencil, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { ReadyGate } from "@/components/ReadyGate";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/field";
import { SearchInput } from "@/components/ui/search-input";
import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel, ListCard } from "@/components/ui/panel";
import { Empty, listItemDescriptionClass, listRowHoverActionsClass, Loading } from "@/components/ui/list-state";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import {
  copyWorkspace,
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  updateWorkspace,
} from "@/api/endpoints";
import { setWorkspaceId } from "@/api/client";
import type { WorkspaceItem } from "@/api/types";
import { useAuth } from "@/app/auth";
import { withWorkspacePrefix } from "@/app/workspace-route";
import { toastAction } from "@/lib/toast-copy";

export function WorkspacesRoute() {
  const { t } = useTranslation();
  const toast = useToast();
  const { confirm } = useDialogs();
  const { me } = useAuth();
  const [items, setItems] = useState<WorkspaceItem[] | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<WorkspaceItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [copyingId, setCopyingId] = useState<string | null>(null);
  const formRef = useRef<HTMLDivElement>(null);

  const currentWorkspaceId = me?.current_workspace_id || "";
  const defaultWorkspaceId = useMemo(
    () => (items ?? []).find((w) => w.is_default)?.id || "",
    [items],
  );
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = items ?? [];
    if (!q) return list;
    return list.filter(
      (w) => w.name.toLowerCase().includes(q) || w.description.toLowerCase().includes(q),
    );
  }, [items, query]);

  const load = async () => {
    try {
      const res = await listWorkspaces();
      setItems(res.items);
    } catch (e) {
      toast((e as Error).message, "error");
      setItems([]);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentWorkspaceId]);

  const switchWorkspace = (workspaceId: string) => {
    setWorkspaceId(workspaceId);
    if (workspaceId === defaultWorkspaceId) {
      window.location.href = "/chat";
      return;
    }
    window.location.href = withWorkspacePrefix("/chat", workspaceId);
  };

  const resetForm = () => {
    setEditing(null);
    setName("");
    setDescription("");
  };

  const submit = async () => {
    const nextName = name.trim();
    if (!nextName) return;
    if (nextName.length > 25) {
      toast(t("workspaces.errors.nameTooLong"), "error");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await updateWorkspace(editing.id, { name: nextName, description: description.trim() });
        toast(toastAction("updated", nextName, "workspace"), "success");
      } else {
        await createWorkspace({ name: nextName, description: description.trim() });
        toast(toastAction("added", nextName, "workspace"), "success");
      }
      resetForm();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (workspace: WorkspaceItem) => {
    const ok = await confirm({
      title: t("workspaces.deleteConfirm.title"),
      body: t("workspaces.deleteConfirm.body", { name: workspace.name }),
      danger: true,
      confirmText: t("common.actions.delete"),
    });
    if (!ok) return;
    try {
      await deleteWorkspace(workspace.id);
      await load();
      if (workspace.id === currentWorkspaceId) {
        setWorkspaceId(defaultWorkspaceId);
        window.location.href = "/chat";
        return;
      }
      toast(toastAction("deleted", workspace.name, "workspace"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const startEdit = (workspace: WorkspaceItem) => {
    setEditing(workspace);
    setName(workspace.name);
    setDescription(workspace.description || "");
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const buildCopyName = (sourceName: string) => {
    const suffix = t("workspaces.copyNameSuffix");
    const maxBase = 25 - suffix.length;
    const base = sourceName.trim().slice(0, Math.max(1, maxBase)).trimEnd();
    return `${base}${suffix}`;
  };

  const duplicate = async (workspace: WorkspaceItem) => {
    const ok = await confirm({
      title: t("workspaces.copyConfirm.title"),
      body: t("workspaces.copyConfirm.body", { name: workspace.name }),
      confirmText: t("workspaces.actions.copy"),
    });
    if (!ok) return;
    setCopyingId(workspace.id);
    try {
      const res = await copyWorkspace(workspace.id, { name: buildCopyName(workspace.name) });
      toast(toastAction("added", res.item.name, "workspace"), "success");
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setCopyingId(null);
    }
  };

  return (
    <PageContainer title={t("workspaces.title")} subtitle={t("workspaces.subtitle")}>
      <ReadyGate>
        <div className="space-y-4">
          <SearchInput value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("workspaces.searchPlaceholder")} />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty text={query ? t("workspaces.noMatch") : t("workspaces.empty")} />
          ) : (
            <div className="space-y-2">
              {filtered.map((w) => {
                const isCurrent = w.id === currentWorkspaceId;
                return (
                  <ListCard key={w.id} className="group p-0 overflow-hidden">
                    <div className="flex items-start justify-between gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-medium">{w.name}</span>
                          {w.is_default && <Badge variant="outline">{t("workspaces.badges.default")}</Badge>}
                          {isCurrent && <Badge variant="brand">{t("workspaces.badges.current")}</Badge>}
                        </div>
                        {w.description && (
                          <p className={listItemDescriptionClass}>{w.description}</p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {!isCurrent && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className={listRowHoverActionsClass}
                            title={t("workspaces.actions.switch")}
                            aria-label={t("workspaces.actions.switch")}
                            onClick={() => switchWorkspace(w.id)}
                          >
                            <Check className="size-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className={listRowHoverActionsClass}
                          title={t("workspaces.actions.edit")}
                          aria-label={t("workspaces.actions.edit")}
                          onClick={() => startEdit(w)}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className={listRowHoverActionsClass}
                          title={t("workspaces.actions.copy")}
                          aria-label={t("workspaces.actions.copy")}
                          disabled={copyingId === w.id}
                          onClick={() => {
                            void duplicate(w);
                          }}
                        >
                          {copyingId === w.id ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Copy className="size-4" />
                          )}
                        </Button>
                        {!w.is_default && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className={listRowHoverActionsClass}
                            title={t("workspaces.actions.delete")}
                            aria-label={t("workspaces.actions.delete")}
                            onClick={() => {
                              void remove(w);
                            }}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </ListCard>
                );
              })}
            </div>
          )}

          <div ref={formRef}>
            <CollapsiblePanel
              summary={editing ? t("workspaces.form.editTitle") : t("workspaces.form.createTitle")}
              defaultOpen={!!editing}
              onOpenChange={(open) => {
                if (!open) resetForm();
              }}
            >
              <div className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label>{t("workspaces.fields.name")}</Label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value.slice(0, 25))}
                    placeholder={t("workspaces.fields.namePlaceholder")}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label>{t("workspaces.fields.description")}</Label>
                  <Textarea
                    rows={2}
                    value={description}
                    onChange={(e) => setDescription(e.target.value.slice(0, 200))}
                    placeholder={t("workspaces.fields.descriptionPlaceholder")}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    disabled={saving || !name.trim()}
                    onClick={() => {
                      void submit();
                    }}
                  >
                    {saving && <Loader2 className="size-4 animate-spin" />}
                    {editing ? t("common.actions.save") : t("common.actions.add")}
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
