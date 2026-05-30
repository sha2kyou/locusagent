import { useEffect, useState } from "react";
import { Copy, KeyRound, Loader2 } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { useAuth } from "@/app/auth";
import { useTheme, type ThemePreference } from "@/app/theme";
import { cn } from "@/lib/utils";
import {
  deleteAccount,
  getLLMConfig,
  getTavilyConfig,
  putLLMConfig,
  putTavilyConfig,
  rotateApiKey,
} from "@/api/endpoints";
import type { LLMConfig } from "@/api/types";

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];
const THEME_OPTION_VALUES = THEME_OPTIONS.map((opt) => opt.value);

interface Props {
  open: boolean;
  onClose: () => void;
  onLogout: () => void;
  required?: boolean;
}

export function SettingsModal({ open, onClose, onLogout, required = false }: Props) {
  const toast = useToast();
  const { confirm } = useDialogs();
  const { me, reload } = useAuth();
  const { preference: themePreference, setPreference: setThemePreference } = useTheme();

  const [cfg, setCfg] = useState<LLMConfig | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("gpt-4o");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [tavilyConfigured, setTavilyConfigured] = useState(false);
  const [tavilyApiKey, setTavilyApiKey] = useState("");
  const [tavilySaving, setTavilySaving] = useState(false);

  const [flashKey, setFlashKey] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const themeIndex = THEME_OPTION_VALUES.indexOf(themePreference);

  const selectThemeByOffset = (offset: number) => {
    const len = THEME_OPTION_VALUES.length;
    const next = (themeIndex + offset + len) % len;
    setThemePreference(THEME_OPTION_VALUES[next]);
  };

  useEffect(() => {
    if (!open) return;
    void Promise.all([getLLMConfig(), getTavilyConfig()]).then(([c, tavily]) => {
      setCfg(c);
      setBaseUrl(c.base_url ?? "");
      setModel(c.model || "gpt-4o");
      setApiKey("");
      setTavilyConfigured(tavily.configured);
      setTavilyApiKey("");
    });
  }, [open]);

  const configured = cfg?.configured ?? false;
  const mustConfigure = required && !configured;
  const dirty = configured
    ? baseUrl !== (cfg?.base_url ?? "") || model !== (cfg?.model ?? "") || apiKey.length >= 8
    : baseUrl.trim().length > 0 && model.trim().length > 0 && apiKey.length >= 8;

  const save = async () => {
    setSaving(true);
    try {
      const body: { base_url: string; model: string; api_key?: string } = { base_url: baseUrl, model };
      if (apiKey.length >= 8) body.api_key = apiKey;
      const next = await putLLMConfig(body);
      setCfg(next);
      setApiKey("");
      const action = next.provision_action;
      toast(
        action === "none" ? "已保存" : "已保存，Agent 正在应用配置（约 30~60 秒）",
        "success",
      );
      await reload();
      if (required && next.configured) onClose();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const rotate = async () => {
    const ok = await confirm({
      title: "重置外部 API Key",
      body: "旧 Key 将立即失效。新 Key 仅显示一次，请妥善保存。",
      confirmText: "重置",
      danger: true,
    });
    if (!ok) return;
    try {
      const { api_key } = await rotateApiKey();
      setFlashKey(api_key);
      await reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const saveTavily = async (clear = false) => {
    const nextKey = clear ? "" : tavilyApiKey.trim();
    if (!clear && nextKey.length > 0 && nextKey.length < 8) {
      toast("Tavily API Key 至少 8 位", "error");
      return;
    }
    setTavilySaving(true);
    try {
      const next = await putTavilyConfig({ api_key: nextKey });
      setTavilyConfigured(next.configured);
      setTavilyApiKey("");
      toast(next.configured ? "Tavily Key 已保存" : "Tavily Key 已清空", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setTavilySaving(false);
    }
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="设置"
        description={mustConfigure ? "首次使用请先完成模型配置，完成前无法关闭。" : "配置主题、对话模型与外部访问"}
        size="lg"
        showClose={!mustConfigure}
        closeDisabled={mustConfigure}
      >
        <div className="space-y-5">
          {/* 主题 */}
          <section className="rounded-lg border border-border bg-surface/40 p-4">
            <h3 className="mb-3 text-sm font-semibold">主题</h3>
            <div
              className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-muted p-1"
              role="radiogroup"
              aria-label="主题"
            >
              {THEME_OPTIONS.map((opt) => {
                const selected = themePreference === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    tabIndex={selected ? 0 : -1}
                    onClick={() => setThemePreference(opt.value)}
                    onKeyDown={(e) => {
                      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                        e.preventDefault();
                        selectThemeByOffset(1);
                        return;
                      }
                      if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                        e.preventDefault();
                        selectThemeByOffset(-1);
                        return;
                      }
                      if (e.key === "Home") {
                        e.preventDefault();
                        setThemePreference(THEME_OPTION_VALUES[0]);
                        return;
                      }
                      if (e.key === "End") {
                        e.preventDefault();
                        setThemePreference(THEME_OPTION_VALUES[THEME_OPTION_VALUES.length - 1]);
                        return;
                      }
                      if (e.key === " " || e.key === "Enter") {
                        e.preventDefault();
                        setThemePreference(opt.value);
                      }
                    }}
                    className={cn(
                      "rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
                      selected
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-secondary-foreground hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </section>

          {/* LLM */}
          <section className="rounded-lg border border-border bg-surface/40 p-4">
            <div className="mb-1 flex items-center gap-2">
              <h3 className="text-sm font-semibold">对话模型</h3>
              {configured && <Badge variant="success">已配置</Badge>}
            </div>
            <p className="mb-3 text-xs text-muted-foreground">
              OpenAI 兼容接口，需自带 API Key。修改后 Agent 将重启以应用（约 30~60 秒）。
            </p>
            <div className="grid gap-3">
              <div className="grid gap-1.5">
                <Label>接口地址 (Base URL)</Label>
                <Input
                  type="url"
                  placeholder="https://api.openai.com/v1"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label>模型 API Key {configured && <span className="opacity-60">（留空表示不修改）</span>}</Label>
                <Input
                  type="password"
                  placeholder="sk-..."
                  autoComplete="off"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label>模型名称</Label>
                <Input value={model} onChange={(e) => setModel(e.target.value)} />
              </div>
              <div>
                <Button variant="primary" disabled={!dirty || saving} onClick={save}>
                  {saving && <Loader2 className="size-4 animate-spin" />}
                  保存
                </Button>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-surface/40 p-4">
            <div className="mb-1 flex items-center gap-2">
              <h3 className="text-sm font-semibold">Tavily API Key</h3>
              <Badge variant="neutral">可选</Badge>
              {tavilyConfigured ? <Badge variant="success">已配置</Badge> : <Badge>未配置</Badge>}
            </div>
            <p className="mb-3 text-xs text-muted-foreground">
              可选配置，每个用户单独保存。输入新 Key 后保存；如需清空，点击「清空」。
            </p>
            <div className="grid gap-3">
              <div className="grid gap-1.5">
                <Label>API Key</Label>
                <Input
                  type="password"
                  placeholder="tvly-..."
                  autoComplete="off"
                  value={tavilyApiKey}
                  onChange={(e) => setTavilyApiKey(e.target.value)}
                />
              </div>
              <div className="flex items-center gap-2">
                <Button variant="primary" disabled={tavilySaving} onClick={() => saveTavily(false)}>
                  {tavilySaving && <Loader2 className="size-4 animate-spin" />}
                  保存
                </Button>
                <Button
                  variant="secondary"
                  disabled={tavilySaving || !tavilyConfigured}
                  onClick={() => saveTavily(true)}
                >
                  清空
                </Button>
              </div>
            </div>
          </section>

          {!mustConfigure ? (
            <>
              {/* 外部 API Key */}
              <section className="rounded-lg border border-border bg-surface/40 p-4">
                <div className="mb-1 flex items-center gap-2">
                  <h3 className="text-sm font-semibold">外部 API Key</h3>
                  {me?.agent_api_key_configured ? (
                    <Badge variant="brand">已签发</Badge>
                  ) : (
                    <Badge>未签发</Badge>
                  )}
                </div>
                <p className="mb-3 text-xs text-muted-foreground">
                  供外部客户端调用 <code className="rounded bg-secondary px-1">/api/v1/*</code>，与上方模型 Key 无关。
                </p>
                <Button variant="secondary" onClick={rotate}>
                  <KeyRound className="size-4" /> 重置外部 API Key
                </Button>
              </section>

              <div className="flex justify-end">
                <Button variant="danger-ghost" size="sm" onClick={() => setDeleteOpen(true)}>
                  删除账户…
                </Button>
              </div>
            </>
          ) : null}
        </div>
      </Modal>

      <ApiKeyFlashModal value={flashKey} onClose={() => setFlashKey(null)} />
      <DeleteAccountModal
        open={deleteOpen}
        username={me?.username ?? ""}
        onClose={() => setDeleteOpen(false)}
        onDeleted={onLogout}
      />
    </>
  );
}

export function ApiKeyFlashModal({ value, onClose }: { value: string | null; onClose: () => void }) {
  const toast = useToast();
  return (
    <Modal
      open={!!value}
      onClose={onClose}
      title="新的外部 API Key"
      description="完整 Key 仅显示一次，关闭后无法再次查看。"
      size="md"
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              if (value) void navigator.clipboard.writeText(value);
              toast("已复制", "success");
            }}
          >
            <Copy className="size-4" /> 复制
          </Button>
          <Button variant="primary" onClick={onClose}>
            我已保存
          </Button>
        </>
      }
    >
      <code className="block break-all rounded-md border border-border bg-surface-2 p-3 font-mono text-sm">
        {value}
      </code>
    </Modal>
  );
}

function DeleteAccountModal({
  open,
  username,
  onClose,
  onDeleted,
}: {
  open: boolean;
  username: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const toast = useToast();
  const [typed, setTyped] = useState("");
  useEffect(() => {
    if (open) setTyped("");
  }, [open]);

  const submit = async () => {
    try {
      await deleteAccount(typed);
      onDeleted();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="删除账户"
      description="将永久删除你的 Agent、对话、记忆与技能等全部数据，无法恢复。"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button variant="danger" disabled={typed !== username} onClick={submit}>
            永久删除
          </Button>
        </>
      }
    >
      <div className="grid gap-1.5">
        <Label>
          输入用户名 <code className="rounded bg-secondary px-1 font-mono">{username}</code> 以确认
        </Label>
        <Input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
    </Modal>
  );
}
