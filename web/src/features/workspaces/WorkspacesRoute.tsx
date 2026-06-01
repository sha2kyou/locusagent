import { useEffect, useMemo, useState } from "react";
import { Check, Pencil, Plus, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { ReadyGate } from "@/components/ReadyGate";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { CollapsiblePanel, ListCard } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  updateWorkspace,
} from "@/api/endpoints";
import { setWorkspaceId } from "@/api/client";
import type { WorkspaceItem } from "@/api/types";
import { useAuth } from "@/app/auth";
import { withWorkspacePrefix } from "@/app/workspace-route";
import { Empty, Loading } from "@/features/skills/SkillsRoute";

export function WorkspacesRoute() {
  const toast = useToast();
  const { confirm } = useDialogs();
  const { me } = useAuth();
  const [items, setItems] = useState<WorkspaceItem[] | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [query, setQuery] = useState("");
  const [editingWorkspace, setEditingWorkspace] = useState<WorkspaceItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [formOpen, setFormOpen] = useState(false);

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

  const submit = async () => {
    const nextName = name.trim();
    if (!nextName) return;
    if (nextName.length > 25) {
      toast("名称不能超过 25 字", "error");
      return;
    }
    setSaving(true);
    try {
      if (editingWorkspace) {
        await updateWorkspace(editingWorkspace.id, { name: nextName, description: description.trim() });
        toast("已更新", "success");
      } else {
        await createWorkspace({ name: nextName, description: description.trim() });
        toast("已添加", "success");
      }
      setName("");
      setDescription("");
      setFormOpen(false);
      setEditingWorkspace(null);
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const removeWorkspace = async (workspace: WorkspaceItem) => {
    const ok = await confirm({
      title: "删除工作区",
      body: `删除「${workspace.name}」后不可恢复，确认删除？`,
      danger: true,
      confirmText: "删除",
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
      toast("已删除工作区", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const startCreate = () => {
    setEditingWorkspace(null);
    setName("");
    setDescription("");
    setFormOpen(true);
  };

  const startEdit = (workspace: WorkspaceItem) => {
    setEditingWorkspace(workspace);
    setName(workspace.name);
    setDescription(workspace.description || "");
    setFormOpen(true);
  };

  return (
    <PageContainer
      title="工作区"
      subtitle="创建、切换与管理工作区"
      actions={
        <Button variant="secondary" size="sm" onClick={startCreate}>
          <Plus className="size-4" /> 新建工作区
        </Button>
      }
    >
      <ReadyGate>
        <div className="space-y-4">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索工作区…" />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty text={query ? "无匹配工作区" : "暂无工作区"} />
          ) : (
            <div className="space-y-2">
              {filtered.map((w) => {
                const isCurrent = w.id === currentWorkspaceId;
                return (
                  <ListCard key={w.id} className="group">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-medium">{w.name}</span>
                          {w.is_default && <Badge variant="outline">默认</Badge>}
                          {isCurrent && <Badge variant="brand">当前</Badge>}
                        </div>
                        {w.description && (
                          <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{w.description}</p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {!isCurrent && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-muted-foreground opacity-100 md:opacity-0 md:group-hover:opacity-100"
                            title="切换到该工作区"
                            aria-label="切换到该工作区"
                            onClick={() => switchWorkspace(w.id)}
                          >
                            <Check className="size-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-muted-foreground opacity-100 md:opacity-0 md:group-hover:opacity-100"
                          title="编辑工作区"
                          aria-label="编辑工作区"
                          onClick={() => startEdit(w)}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        {!w.is_default && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-muted-foreground opacity-100 hover:text-destructive md:opacity-0 md:group-hover:opacity-100"
                            title="删除工作区"
                            aria-label="删除工作区"
                            onClick={() => {
                              void removeWorkspace(w);
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

          <CollapsiblePanel summary={editingWorkspace ? "编辑工作区" : "新建工作区"} defaultOpen={formOpen}>
            <div className="grid gap-3">
              <div className="grid gap-1.5">
                <Label>名称（25 字内）</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value.slice(0, 25))}
                  placeholder="输入工作区名称"
                />
              </div>
              <div className="grid gap-1.5">
                <Label>描述（可选）</Label>
                <Textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value.slice(0, 200))}
                  placeholder="输入工作区描述"
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
                  {editingWorkspace ? "保存" : "添加"}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setEditingWorkspace(null);
                    setFormOpen(false);
                    setName("");
                    setDescription("");
                  }}
                >
                  取消
                </Button>
              </div>
            </div>
          </CollapsiblePanel>
        </div>
      </ReadyGate>
    </PageContainer>
  );
}

