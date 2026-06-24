import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { getDesktopPrefs, setDesktopPrefs } from "@/lib/desktop-prefs";
import { isDesktopPrefsPartialSaveError } from "@/lib/desktop-prefs-errors";
import { SettingsSection } from "./SettingsSection";
import { ShortcutCapture } from "./ShortcutCapture";

/** 桌面版快捷对话全局快捷键（通用页 + 快捷对话页共用） */
export function DesktopQuickChatPrefsSection() {
  const { t } = useTranslation();
  const toast = useToast();
  const [enabled, setEnabled] = useState(true);
  const [alwaysOnTop, setAlwaysOnTop] = useState(true);
  const [shortcut, setShortcut] = useState("cmd+shift+K");
  const [registered, setRegistered] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void getDesktopPrefs().then((prefs) => {
      setEnabled(prefs.quick_chat_enabled ?? true);
      setAlwaysOnTop(prefs.quick_chat_always_on_top ?? true);
      setShortcut(prefs.quick_chat_shortcut || "cmd+shift+K");
      setRegistered(prefs.quick_chat_shortcut_registered ?? false);
      setRegisterError(prefs.quick_chat_shortcut_error ?? null);
    });
  }, []);

  const refreshStatus = async () => {
    const prefs = await getDesktopPrefs();
    setRegistered(prefs.quick_chat_shortcut_registered ?? false);
    setRegisterError(prefs.quick_chat_shortcut_error ?? null);
    return prefs;
  };

  const save = async () => {
    setSaving(true);
    try {
      const current = await getDesktopPrefs();
      const next = await setDesktopPrefs({
        run_in_background: current.run_in_background,
        launch_at_login: current.launch_at_login,
        quick_chat_enabled: enabled,
        quick_chat_shortcut: shortcut.trim() || "cmd+shift+K",
        quick_chat_always_on_top: alwaysOnTop,
      });
      setEnabled(next.quick_chat_enabled);
      setAlwaysOnTop(next.quick_chat_always_on_top);
      setShortcut(next.quick_chat_shortcut);
      await refreshStatus();
      toast(t("settings.general.desktopPrefsSaved"), "success");
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (isDesktopPrefsPartialSaveError(message)) {
        try {
          const next = await refreshStatus();
          setEnabled(next.quick_chat_enabled);
          setAlwaysOnTop(next.quick_chat_always_on_top);
          setShortcut(next.quick_chat_shortcut);
        } catch {
          // ignore
        }
      }
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsSection
      title={t("settings.general.quickChat.title")}
      description={t("settings.general.quickChat.description")}
    >
      <div className="grid max-w-xl gap-4">
        <label className="flex cursor-pointer items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          <span>
            {t("settings.general.quickChat.enabled.label")}
            <span className="mt-1 block text-xs text-muted-foreground">
              {t("settings.general.quickChat.enabled.hint")}
            </span>
          </span>
        </label>
        <label className="flex cursor-pointer items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={alwaysOnTop}
            onChange={(e) => setAlwaysOnTop(e.target.checked)}
            disabled={!enabled || saving}
          />
          <span>
            {t("settings.general.quickChat.alwaysOnTop.label")}
            <span className="mt-1 block text-xs text-muted-foreground">
              {t("settings.general.quickChat.alwaysOnTop.hint")}
            </span>
          </span>
        </label>
        <ShortcutCapture value={shortcut} onChange={setShortcut} disabled={!enabled || saving} />
        {enabled && registerError ? (
          <p className="text-xs text-destructive">
            {t("settings.general.quickChat.shortcut.error", { error: registerError })}
          </p>
        ) : enabled && registered ? (
          <p className="text-xs text-emerald-600 dark:text-emerald-400">
            {t("settings.general.quickChat.shortcut.active")}
          </p>
        ) : enabled ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            {t("settings.general.quickChat.shortcut.inactive")}
          </p>
        ) : null}
        <div>
          <Button variant="primary" disabled={saving} onClick={() => void save()}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            {t("common.actions.save")}
          </Button>
        </div>
      </div>
    </SettingsSection>
  );
}
