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
  getTimezoneConfig,
  putTimezoneConfig,
  rotateApiKey,
} from "@/api/endpoints";
import { UsageSummaryCard } from "./UsageSummaryCard";

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];
const THEME_OPTION_VALUES = THEME_OPTIONS.map((opt) => opt.value);

const TIMEZONE_OPTIONS = [
  "UTC",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Asia/Hong_Kong",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
];

interface Props {
  open: boolean;
  onClose: () => void;
  onLogout: () => void;
}

export function SettingsModal({ open, onClose, onLogout }: Props) {
  const toast = useToast();
  const { confirm } = useDialogs();
  const { me, reload } = useAuth();
  const { preference: themePreference, setPreference: setThemePreference } = useTheme();

  const [timezone, setTimezone] = useState("UTC");
  const [timezoneSaving, setTimezoneSaving] = useState(false);

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
    void getTimezoneConfig().then((tz) => {
      setTimezone(tz.timezone || "UTC");
    });
  }, [open]);

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

  const saveTimezone = async () => {
    setTimezoneSaving(true);
    try {
      const next = await putTimezoneConfig({ timezone: timezone.trim() || "UTC" });
      setTimezone(next.timezone);
      toast(`时区已保存：${next.timezone}`, "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setTimezoneSaving(false);
    }
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="设置"
        description="主题、时区与外部 API 访问"
        size="lg"
      >
        <div className="space-y-5">
          <UsageSummaryCard active={open} />

          <section className="rounded-lg border border-border bg-surface/40 p-4">
            <h3 className="mb-3 text-sm font-semibold">主题</h3>
            <div
              className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-surface/40 p-1"
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
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg border border-border bg-surface/40 p-4">
            <h3 className="mb-1 text-sm font-semibold">时区</h3>
            <p className="mb-3 text-xs text-muted-foreground">
              用于定时任务 Cron 与单次执行时间，默认 UTC。
            </p>
            <div className="grid gap-3">
              <div className="grid gap-1.5">
                <Label>时区</Label>
                <Input
                  list="timezone-options"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  placeholder="UTC"
                />
                <datalist id="timezone-options">
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <option key={tz} value={tz} />
                  ))}
                </datalist>
              </div>
              <div>
                <Button variant="primary" disabled={timezoneSaving} onClick={() => void saveTimezone()}>
                  {timezoneSaving && <Loader2 className="size-4 animate-spin" />}
                  保存时区
                </Button>
              </div>
            </div>
          </section>

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
              供外部客户端调用 <code className="rounded bg-secondary px-1">/api/v1/*</code>。
              对话模型由服务端环境变量统一配置。
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
      description="将永久删除你的 AgentPod、对话、记忆与技能等全部数据，无法恢复。"
      size="sm"
      footer={
        <Button variant="danger" disabled={typed !== username} onClick={submit}>
          永久删除
        </Button>
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
