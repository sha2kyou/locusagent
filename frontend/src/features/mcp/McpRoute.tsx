import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { SearchInput } from "@/components/ui/search-input";
import { Empty, listItemBriefClass, listRowHoverActionsClass, Loading } from "@/components/ui/list-state";
import { Tag } from "@/components/ui/tag";
import { getWorkspaceId } from "@/api/client";
import { createMcp, deleteMcp, disconnectMcpOAuth, getMcpOAuthAuthorizeUrl, listMcp, reconnectMcp, updateMcp } from "@/api/endpoints";
import type { McpInput, McpServer, McpTool } from "@/api/types";
import i18n from "@/i18n";
import { openExternalUrl } from "@/lib/open-external";
import { pollMcpOAuthConnected } from "@/lib/mcp-oauth";
import { toastAction } from "@/lib/toast-copy";

function parseKvJson(raw: string, label: string): Record<string, string> {
  const source = raw.trim() || "{}";
  let parsed: unknown;
  try {
    parsed = JSON.parse(source);
  } catch {
    throw new Error(i18n.t("mcp.validation.jsonParseFailed", { label }));
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(i18n.t("mcp.validation.mustBeObject", { label }));
  }
  const entries = Object.entries(parsed as Record<string, unknown>);
  const out: Record<string, string> = {};
  for (const [k, v] of entries) {
    const key = k.trim();
    if (!key) throw new Error(i18n.t("mcp.validation.keyEmpty", { label }));
    if (typeof v !== "string") throw new Error(i18n.t("mcp.validation.valueMustBeString", { label, key }));
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

function mcpConnectionStatus(s: McpServer): {
  label: string;
  variant: "success" | "warning" | "danger";
  dotClass: string;
} {
  if (s.pending) {
    return { label: i18n.t("mcp.status.connecting"), variant: "warning", dotClass: "bg-warning" };
  }
  if (s.connected) {
    return { label: i18n.t("mcp.status.online"), variant: "success", dotClass: "bg-success" };
  }
  return { label: i18n.t("mcp.status.offline"), variant: "danger", dotClass: "bg-destructive" };
}

export function McpRoute() {
  const { t } = useTranslation();
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<McpServer[] | null>(null);
  const [query, setQuery] = useState("");
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
  const [oauthPending, setOauthPending] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const envLabel = t("mcp.form.validation.env");
  const headersLabel = t("mcp.form.validation.headers");

  const load = async (opts?: { sync?: boolean; silent?: boolean }) => {
    try {
      const { items } = await listMcp(opts);
      setItems(items);
    } catch (e) {
      if (!opts?.silent) toast((e as Error).message, "error");
      if (!opts?.silent) setItems([]);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const hasPending = (items ?? []).some((s) => s.pending);
    if (hasPending && !pollRef.current) {
      pollRef.current = window.setInterval(() => void load({ sync: true, silent: true }), 2000);
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

  const startOAuth = async (s: McpServer) => {
    const workspaceId = getWorkspaceId();
    if (!workspaceId) {
      toast(t("mcp.selectWorkspace"), "error");
      return;
    }
    setOauthPending(s.name);
    try {
      const { authorize_url: authorizeUrl } = await getMcpOAuthAuthorizeUrl(s.name, workspaceId);
      await openExternalUrl(authorizeUrl);
      toast(t("mcp.oauthFlow.browserOpened", { name: s.name }), "info");
      const ok = await pollMcpOAuthConnected(s.name);
      if (ok) {
        toast(t("mcp.oauthFlow.success", { name: s.name }), "success");
        await load({ sync: true });
      } else {
        toast(t("mcp.oauthFlow.incomplete", { name: s.name }), "error");
      }
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setOauthPending(null);
    }
  };

  useEffect(() => {
    if (transport !== "stdio") {
      setEnvError(null);
      return;
    }
    try {
      parseKvJson(envJson, envLabel);
      setEnvError(null);
    } catch (e) {
      setEnvError((e as Error).message);
    }
  }, [envJson, transport, envLabel]);

  useEffect(() => {
    if (transport !== "http") {
      setHeadersError(null);
      return;
    }
    try {
      parseKvJson(headersJson, headersLabel);
      setHeadersError(null);
    } catch (e) {
      setHeadersError((e as Error).message);
    }
  }, [headersJson, transport, headersLabel]);

  const buildPayload = (): McpInput => {
    if (transport === "stdio") {
      const env = parseKvJson(envJson, envLabel);
      const base: McpInput = {
        name,
        transport,
        command: command.trim().split(/\s+/).filter(Boolean),
        args: [],
      };
      if (Object.keys(env).length > 0) base.env = env;
      return base;
    }
    const headers = parseKvJson(headersJson, headersLabel);
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
      setEnvJson(JSON.stringify(parseKvJson(envJson, envLabel), null, 2));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const formatHeadersJson = () => {
    try {
      setHeadersJson(JSON.stringify(parseKvJson(headersJson, headersLabel), null, 2));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const submit = async () => {
    setSaving(true);
    try {
      const label = name.trim();
      const saved = editing
        ? await updateMcp(editing, buildPayload())
        : await createMcp(buildPayload());
      if (saved.pending) {
        toast(t("mcp.oauthFlow.connecting", { name: saved.name }), "info");
      } else {
        toast(toastAction(editing ? "updated" : "added", label, "mcpService"), "success");
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
    setReconnecting(s.name);
    try {
      const saved = await reconnectMcp(s.name);
      if (saved.pending) {
        toast(t("mcp.oauthFlow.reconnecting", { name: s.name }), "info");
      } else {
        toast(toastAction("reconnected", s.name, "mcpService"), "success");
      }
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setReconnecting(null);
    }
  };

  const disconnectOAuth = async (s: McpServer) => {
    try {
      await disconnectMcpOAuth(s.name);
      try {
        await reconnectMcp(s.name);
      } catch {
        // expected when no token
      }
      toast(toastAction("oauthDisconnected", s.name, "mcpService"), "success");
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const remove = async (s: McpServer) => {
    if (
      !(await confirm({
        title: t("mcp.form.deleteTitle"),
        body: t("mcp.form.deleteBody", { name: s.name }),
        danger: true,
        confirmText: t("common.actions.delete"),
      }))
    ) {
      return;
    }
    try {
      await deleteMcp(s.name);
      if (editing === s.name) reset();
      await load();
      toast(toastAction("deleted", s.name, "mcpService"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const formInvalid = !!envError || !!headersError;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = items ?? [];
    if (!q) return list;
    return list.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.url || "").toLowerCase().includes(q) ||
        (s.command ?? []).join(" ").toLowerCase().includes(q),
    );
  }, [items, query]);

  return (
    <PageContainer
      title={t("mcp.title")}
      subtitle={t("mcp.subtitle")}
      actions={items ? <Badge variant="outline">{t("mcp.serviceCount", { count: items.length })}</Badge> : undefined}
    >
      <ReadyGate>
        <div className="space-y-4">
          <SearchInput
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("mcp.searchPlaceholder")}
          />

          {items === null ? (
            <Loading />
          ) : filtered.length === 0 ? (
            <Empty text={query ? t("mcp.noMatch") : t("mcp.empty")} />
          ) : (
            <div className="space-y-2">
              {filtered.map((s) => {
                const status = mcpConnectionStatus(s);
                return (
                <ListCard key={s.name} className="group p-0 overflow-hidden">
                  <div className="flex items-start justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <span className="min-w-0 font-medium">{s.name}</span>
                        <Badge variant={status.variant}>
                          <Dot className={status.dotClass} />
                          {status.label}
                        </Badge>
                        <Badge>{s.transport}</Badge>
                        {s.oauth_required ? (
                          <Badge variant={s.oauth_connected ? "success" : "outline"}>
                            {s.oauth_connected ? (
                              <ShieldCheck className="size-3.5" aria-hidden />
                            ) : (
                              <KeyRound className="size-3.5" aria-hidden />
                            )}
                            {s.oauth_connected ? t("mcp.oauth.connected") : t("mcp.oauth.pending")}
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
                          className={listRowHoverActionsClass}
                          disabled={oauthPending === s.name}
                          onClick={() => void startOAuth(s)}
                          aria-label={t("mcp.actions.oauthAuthorize")}
                          title={t("mcp.actions.oauthAuthorize")}
                        >
                          {oauthPending === s.name ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <KeyRound />
                          )}
                        </Button>
                      ) : null}
                      {s.oauth_required && s.oauth_connected ? (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className={listRowHoverActionsClass}
                          onClick={() => disconnectOAuth(s)}
                          aria-label={t("mcp.actions.disconnectOAuth")}
                          title={t("mcp.actions.disconnectOAuth")}
                        >
                          <ShieldOff />
                        </Button>
                      ) : null}
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className={listRowHoverActionsClass}
                        disabled={reconnecting === s.name || s.pending}
                        onClick={() => void reconnect(s)}
                        aria-label={t("mcp.actions.reconnect")}
                      >
                        {reconnecting === s.name || s.pending ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <RefreshCw />
                        )}
                      </Button>
                      <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => startEdit(s)} aria-label={t("common.actions.edit")}><Pencil /></Button>
                      <Button variant="ghost" size="icon-sm" className={listRowHoverActionsClass} onClick={() => remove(s)} aria-label={t("common.actions.delete")}><Trash2 /></Button>
                    </div>
                  </div>
                  <CollapsibleSection summary={t("common.actions.details")}>
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
                          {s.tools.map((tool) => (
                            <Tag
                              key={tool.full_name}
                              onClick={() => setSelectedTool({ serverName: s.name, tool })}
                            >
                              {tool.name}
                            </Tag>
                          ))}
                        </div>
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
            summary={editing ? t("mcp.form.editSummary", { name: editing }) : t("mcp.form.addTitle")}
            defaultOpen={!!editing}
            onOpenChange={(open) => {
              if (!open) reset();
            }}
          >
            <div className="grid gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label>{t("mcp.fields.name")}</Label>
                  <Input value={name} disabled={!!editing} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="grid gap-1.5">
                  <Label>{t("mcp.fields.transport")}</Label>
                  <Select value={transport} onChange={(e) => setTransport(e.target.value as "stdio" | "http")}>
                    <option value="stdio">stdio</option>
                    <option value="http">http</option>
                  </Select>
                </div>
              </div>
              {transport === "stdio" ? (
                <div className="grid gap-1.5">
                  <Label>{t("mcp.fields.command")}</Label>
                  <Input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npx @scope/mcp-server" />
                </div>
              ) : (
                <div className="grid gap-1.5">
                  <Label>{t("mcp.fields.url")}</Label>
                  <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://mcp.notion.com/mcp" />
                </div>
              )}
              {transport === "stdio" ? (
                <div className="grid gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label>{t("mcp.fields.envJson")}</Label>
                    <Button variant="ghost" size="sm" onClick={formatEnvJson}>
                      {t("mcp.fields.format")}
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
                    <Label>{t("mcp.fields.headersJson")}</Label>
                    <Button variant="ghost" size="sm" onClick={formatHeadersJson}>
                      {t("mcp.fields.format")}
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
                      ? t("mcp.headersHint.preserve")
                      : t("mcp.headersHint.oauth")}
                  </p>
                </div>
              )}
              <div className="flex gap-2">
                <Button variant="primary" disabled={saving || !name.trim() || formInvalid} onClick={submit}>
                  {saving && <Loader2 className="size-4 animate-spin" />}
                  {editing ? t("common.actions.save") : t("common.actions.add")}
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
              <h3 className="text-sm font-medium">{t("mcp.toolDetail.description")}</h3>
              <p className="whitespace-pre-wrap text-sm text-foreground">
                {normalizeText(selectedTool.tool.description, t("mcp.toolDetail.noDescription"))}
              </p>
            </section>
            <section className="space-y-1">
              <h3 className="text-sm font-medium">{t("mcp.toolDetail.paramsSummary")}</h3>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                {normalizeText(selectedTool.tool.schema_summary, t("mcp.toolDetail.noParamsSummary"))}
              </p>
            </section>
            <section className="space-y-1">
              <h3 className="text-sm font-medium">{t("mcp.toolDetail.inputSchema")}</h3>
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
