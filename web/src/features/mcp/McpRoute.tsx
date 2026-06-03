import { useEffect, useRef, useState } from "react";
import { KeyRound, Loader2, Pencil, RefreshCw, ShieldCheck, ShieldOff, Trash2 } from "lucide-react";
import { PageContainer } from "@/components/PageContainer";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/field";
import { Badge, Dot } from "@/components/ui/badge";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { Drawer } from "@/components/ui/drawer";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { ReadyGate } from "@/components/ReadyGate";
import { useReloadOnAgentRecovery } from "@/hooks/useReloadOnAgentRecovery";
import { Empty, listItemBriefClass, Loading } from "@/components/ui/list-state";
import { Tag } from "@/components/ui/tag";
import { getWorkspaceId } from "@/api/client";
import { createMcp, deleteMcp, disconnectMcpOAuth, listMcp, reconnectMcp, updateMcp } from "@/api/endpoints";
import type { McpInput, McpServer, McpTool } from "@/api/types";
import { toastAction } from "@/lib/toast-copy";

function parseKvJson(raw: string, label: string): Record<string, string> {
  const source = raw.trim() || "{}";
  let parsed: unknown;
  try {
    parsed = JSON.parse(source);
  } catch {
    throw new Error(`${label} JSON 解析失败`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label}必须是 JSON 对象`);
  }
  const entries = Object.entries(parsed as Record<string, unknown>);
  const out: Record<string, string> = {};
  for (const [k, v] of entries) {
    const key = k.trim();
    if (!key) throw new Error(`${label} key 不能为空`);
    if (typeof v !== "string") throw new Error(`${label} ${key} 的值必须是字符串`);
    out[key] = v;
  }
  return out;
}

function kvToJsonText(data?: Record<string, string>): string {
  const keys = Object.keys(data ?? {});
  if (keys.length === 0) return "";
  return JSON.stringify(data, null, 2);
}

function normalizeText(value: unknown, fallback: string): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || fallback;
  }
  if (value == null) return fallback;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return fallback;
  }
}

export function McpRoute() {
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<McpServer[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [transport, setTransport] = useState<"stdio" | "http">("stdio");
  const [command, setCommand] = useState("");
  const [url, setUrl] = useState("");
  const [envJson, setEnvJson] = useState("");
  const [headersJson, setHeadersJson] = useState("");
  const [headersConfigured, setHeadersConfigured] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedTool, setSelectedTool] = useState<{ serverName: string; tool: McpTool } | null>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const [envError, setEnvError] = useState<string | null>(null);
  const [headersError, setHeadersError] = useState<string | null>(null);

  const load = async (opts?: { sync?: boolean }) => {
    try {
      const { items } = await listMcp(opts);
      setItems(items);
    } catch (e) {
      toast((e as Error).message, "error");
      setItems([]);
    }
  };
  useReloadOnAgentRecovery(load);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauth = params.get("oauth");
    const server = params.get("server");
    if (oauth === "success") {
      toast(server ? `「${server}」OAuth 授权成功` : "OAuth 授权成功", "success");
      void load();
      params.delete("oauth");
      params.delete("server");
      const next = `${window.location.pathname}${params.toString() ? `?${params}` : ""}`;
      window.history.replaceState(null, "", next);
    } else if (oauth === "error") {
      toast("OAuth 授权失败", "error");
      params.delete("oauth");
      params.delete("server");
      const next = `${window.location.pathname}${params.toString() ? `?${params}` : ""}`;
      window.history.replaceState(null, "", next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (transport !== "stdio") {
      setEnvError(null);
      return;
    }
    try {
      parseKvJson(envJson, "环境变量");
      setEnvError(null);
    } catch (e) {
      setEnvError((e as Error).message);
    }
  }, [envJson, transport]);

  useEffect(() => {
    if (transport !== "http") {
      setHeadersError(null);
      return;
    }
    try {
      parseKvJson(headersJson, "请求头");
      setHeadersError(null);
    } catch (e) {
      setHeadersError((e as Error).message);
    }
  }, [headersJson, transport]);

  const buildPayload = (): McpInput => {
    if (transport === "stdio") {
      const env = parseKvJson(envJson, "环境变量");
      const base: McpInput = {
        name,
        transport,
        command: command.trim().split(/\s+/).filter(Boolean),
        args: [],
      };
      if (Object.keys(env).length > 0) base.env = env;
      return base;
    }
    const headers = parseKvJson(headersJson, "请求头");
    const base: McpInput = { name, transport, url: url.trim() };
    if (Object.keys(headers).length > 0) base.headers = headers;
    return base;
  };

  const reset = () => {
    setEditing(null);
    setName("");
    setTransport("stdio");
    setCommand("");
    setUrl("");
    setEnvJson("");
    setHeadersJson("");
    setHeadersConfigured(false);
    setEnvError(null);
    setHeadersError(null);
  };

  const startEdit = (s: McpServer) => {
    setEditing(s.name);
    setName(s.name);
    setTransport(s.transport);
    setCommand((s.command ?? []).join(" "));
    setUrl(s.url ?? "");
    setEnvJson(kvToJsonText(s.env));
    const hasHeaders = Object.keys(s.headers ?? {}).length > 0;
    setHeadersJson(hasHeaders ? "" : kvToJsonText(s.headers));
    setHeadersConfigured(hasHeaders);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const formatEnvJson = () => {
    try {
      setEnvJson(JSON.stringify(parseKvJson(envJson, "环境变量"), null, 2));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const formatHeadersJson = () => {
    try {
      setHeadersJson(JSON.stringify(parseKvJson(headersJson, "请求头"), null, 2));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const submit = async () => {
    setSaving(true);
    try {
      if (editing) {
        await updateMcp(editing, buildPayload());
        toast(toastAction("已更新", editing, "MCP 服务"), "success");
      } else {
        await createMcp(buildPayload());
        toast(toastAction("已添加", name.trim(), "MCP 服务"), "success");
      }
      reset();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const reconnect = async (s: McpServer) => {
    try {
      await reconnectMcp(s.name);
      toast(toastAction("已重连", s.name, "MCP 服务"), "success");
      await load({ sync: true });
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const startOAuth = (s: McpServer) => {
    const workspaceId = getWorkspaceId();
    if (!workspaceId) {
      toast("请先选择工作区", "error");
      return;
    }
    const params = new URLSearchParams({ server: s.name, workspace_id: workspaceId });
    window.location.href = `/api/oauth/mcp/start?${params.toString()}`;
  };

  const disconnectOAuth = async (s: McpServer) => {
    try {
      await disconnectMcpOAuth(s.name);
      try {
        await reconnectMcp(s.name);
      } catch {
        // 预期：无 token 时重连失败
      }
      toast(toastAction("已断开 OAuth", s.name, "MCP 服务"), "success");
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const remove = async (s: McpServer) => {
    if (!(await confirm({ title: "删除 MCP 服务", body: `删除「${s.name}」？`, danger: true, confirmText: "删除" }))) return;
    try {
      await deleteMcp(s.name);
      if (editing === s.name) reset();
      await load();
      toast(toastAction("已删除", s.name, "MCP 服务"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const formInvalid = !!envError || !!headersError;

  return (
    <PageContainer
      title="MCP"
      subtitle="MCP 服务连接与工具管理"
      actions={items ? <Badge variant="outline">{items.length} 个服务</Badge> : undefined}
    >
      <ReadyGate>
        <div className="space-y-4">
          {items === null ? (
            <Loading />
          ) : items.length === 0 ? (
            <Empty text="暂无 MCP 服务" />
          ) : (
            <div className="space-y-2">
              {items.map((s) => (
                <ListCard key={s.name} className="p-0 overflow-hidden">
                  <div className="flex items-start justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <span className="min-w-0 font-medium">{s.name}</span>
                        <Badge variant={s.connected ? "success" : "danger"}>
                          <Dot className={s.connected ? "bg-success" : "bg-destructive"} />
                          {s.connected ? "在线" : "离线"}
                        </Badge>
                        <Badge>{s.transport}</Badge>
                        {s.oauth_required ? (
                          <Badge variant={s.oauth_connected ? "success" : "outline"}>
                            {s.oauth_connected ? (
                              <ShieldCheck className="size-3.5" aria-hidden />
                            ) : (
                              <KeyRound className="size-3.5" aria-hidden />
                            )}
                            {s.oauth_connected ? "已授权" : "待授权"}
                          </Badge>
                        ) : null}
                      </div>
                      <p className={listItemBriefClass}>
                        {s.transport === "http" ? s.url : (s.command ?? []).join(" ")}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {s.oauth_required && !s.oauth_connected ? (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => startOAuth(s)}
                          aria-label="OAuth 授权"
                          title="OAuth 授权"
                        >
                          <KeyRound />
                        </Button>
                      ) : null}
                      {s.oauth_required && s.oauth_connected ? (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => disconnectOAuth(s)}
                          aria-label="解除 OAuth 授权"
                          title="解除 OAuth 授权"
                        >
                          <ShieldOff />
                        </Button>
                      ) : null}
                      <Button variant="ghost" size="icon-sm" onClick={() => reconnect(s)} aria-label="重连"><RefreshCw /></Button>
                      <Button variant="ghost" size="icon-sm" onClick={() => startEdit(s)} aria-label="编辑"><Pencil /></Button>
                      <Button variant="ghost" size="icon-sm" onClick={() => remove(s)} aria-label="删除"><Trash2 /></Button>
                    </div>
                  </div>
                  <CollapsibleSection summary="详情">
                    <div className="space-y-2 text-sm">
                      <p className="break-all text-foreground">
                        {s.transport === "http" ? s.url : (s.command ?? []).join(" ")}
                      </p>
                      {Object.keys(s.env ?? {}).length > 0 ? (
                        <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md bg-surface-2 p-2 font-mono text-xs text-foreground">
                          {JSON.stringify(s.env, null, 2)}
                        </pre>
                      ) : null}
                      {Object.keys(s.headers ?? {}).length > 0 ? (
                        <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md bg-surface-2 p-2 font-mono text-xs text-foreground">
                          {JSON.stringify(s.headers, null, 2)}
                        </pre>
                      ) : null}
                      {s.runtime_error && <p className="text-xs text-destructive">{s.runtime_error}</p>}
                      {s.tools.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {s.tools.map((t) => (
                            <Tag
                              key={t.full_name}
                              onClick={() => setSelectedTool({ serverName: s.name, tool: t })}
                            >
                              {t.name}
                            </Tag>
                          ))}
                        </div>
                      )}
                    </div>
                  </CollapsibleSection>
                </ListCard>
              ))}
            </div>
          )}

          <div ref={formRef}>
          <CollapsiblePanel
            summary={editing ? `编辑服务：${editing}` : "添加 MCP 服务"}
            defaultOpen={!!editing}
            onOpenChange={(open) => {
              if (!open) reset();
            }}
          >
            <div className="grid gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label>名称（唯一）</Label>
                  <Input value={name} disabled={!!editing} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="grid gap-1.5">
                  <Label>传输方式</Label>
                  <Select value={transport} onChange={(e) => setTransport(e.target.value as "stdio" | "http")}>
                    <option value="stdio">stdio</option>
                    <option value="http">http</option>
                  </Select>
                </div>
              </div>
              {transport === "stdio" ? (
                <div className="grid gap-1.5">
                  <Label>命令</Label>
                  <Input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npx @scope/mcp-server" />
                </div>
              ) : (
                <div className="grid gap-1.5">
                  <Label>URL</Label>
                  <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://mcp.notion.com/mcp" />
                </div>
              )}
              {transport === "stdio" ? (
                <div className="grid gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label>环境变量（JSON）</Label>
                    <Button variant="ghost" size="sm" onClick={formatEnvJson}>
                      格式化
                    </Button>
                  </div>
                  <Textarea
                    rows={8}
                    value={envJson}
                    onChange={(e) => setEnvJson(e.target.value)}
                    placeholder={'{\n  "API_KEY": "xxx"\n}'}
                    className="font-mono text-xs"
                  />
                  {envError ? <p className="text-xs text-destructive">{envError}</p> : null}
                </div>
              ) : (
                <div className="grid gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label>请求头（JSON）</Label>
                    <Button variant="ghost" size="sm" onClick={formatHeadersJson}>
                      格式化
                    </Button>
                  </div>
                  <Textarea
                    rows={8}
                    value={headersJson}
                    onChange={(e) => setHeadersJson(e.target.value)}
                    placeholder={'{\n  "Authorization": "Bearer ghp_xxx"\n}'}
                    className="font-mono text-xs"
                  />
                  {headersError ? <p className="text-xs text-destructive">{headersError}</p> : null}
                  <p className="text-xs text-muted-foreground">
                    {editing && headersConfigured
                      ? "已配置请求头，留空则保留；填写则覆盖。"
                      : "保存时会自动探测是否支持 OAuth；支持则显示授权按钮，否则在此填写请求头凭据。"}
                  </p>
                </div>
              )}
              <div className="flex gap-2">
                <Button variant="primary" disabled={saving || !name.trim() || formInvalid} onClick={submit}>
                  {saving && <Loader2 className="size-4 animate-spin" />}
                  {editing ? "保存" : "添加"}
                </Button>
              </div>
            </div>
          </CollapsiblePanel>
          </div>
        </div>
      </ReadyGate>
      <Drawer
        open={!!selectedTool}
        onClose={() => setSelectedTool(null)}
        title={selectedTool?.tool.name}
        description={selectedTool ? `${selectedTool.serverName} · ${selectedTool.tool.full_name}` : undefined}
      >
        {selectedTool ? (
          <div className="space-y-4">
            <section className="space-y-1">
              <h3 className="text-sm font-medium">描述</h3>
              <p className="whitespace-pre-wrap text-sm text-foreground">
                {normalizeText(selectedTool.tool.description, "无描述")}
              </p>
            </section>
            <section className="space-y-1">
              <h3 className="text-sm font-medium">参数摘要</h3>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                {normalizeText(selectedTool.tool.schema_summary, "无参数摘要")}
              </p>
            </section>
            <section className="space-y-1">
              <h3 className="text-sm font-medium">输入 Schema</h3>
              <pre className="max-h-[45vh] overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-mono text-xs text-foreground">
                {JSON.stringify(selectedTool.tool.input_schema ?? {}, null, 2)}
              </pre>
            </section>
          </div>
        ) : null}
      </Drawer>
    </PageContainer>
  );
}
