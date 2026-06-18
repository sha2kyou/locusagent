import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Loader2, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/field";
import { SegmentControl } from "@/components/ui/segment-control";
import { useToast } from "@/components/ui/toast";
import { useDialogs } from "@/components/ui/dialogs";
import { useTheme, type ThemePreference } from "@/app/theme";
import { useRefreshAppTimezone, useAppTimezone } from "@/lib/use-app-timezone";
import { putTimezoneConfig, exportSettings, importSettings } from "@/api/endpoints";
import { getDesktopPrefs, isDesktopPrefsAvailable, setDesktopPrefs } from "@/lib/desktop-prefs";
import { isDesktopPrefsPartialSaveError } from "@/lib/desktop-prefs-errors";
import { persistAppLocale } from "@/lib/app-locale";
import { applyDesktopDevtoolsSettings } from "@/lib/desktop-devtools";
import { isDesktopApp } from "@/lib/desktop-app";
import { SUPPORTED_LOCALES, type AppLocale } from "@/i18n";
import { SettingsSection } from "./SettingsSection";

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

export function SettingsGeneralPage() {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const dialogs = useDialogs();
  const importInputRef = useRef<HTMLInputElement>(null);
  const { preference: themePreference, setPreference: setThemePreference } = useTheme();
  const appTimeZone = useAppTimezone();
  const refreshAppTimeZone = useRefreshAppTimezone();
  const [timezone, setTimezone] = useState("UTC");
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [runInBackground, setRunInBackground] = useState(false);
  const [launchAtLogin, setLaunchAtLogin] = useState(false);
  const [desktopPrefsSaving, setDesktopPrefsSaving] = useState(false);
  const [localeSaving, setLocaleSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const desktopPrefsAvailable = isDesktopPrefsAvailable();

  const themeOptions = useMemo(
    (): { value: ThemePreference; label: string }[] => [
      { value: "system", label: t("settings.general.theme.system") },
      { value: "light", label: t("settings.general.theme.light") },
      { value: "dark", label: t("settings.general.theme.dark") },
    ],
    [t],
  );

  const languageOptions = useMemo(
    () =>
      SUPPORTED_LOCALES.map((locale) => ({
        value: locale,
        label: t(`settings.general.language.options.${locale}`),
      })),
    [t],
  );

  const appLocale: AppLocale = i18n.language === "en" ? "en" : "zh";

  const changeLocale = async (locale: AppLocale) => {
    if (locale === appLocale || localeSaving) return;
    setLocaleSaving(true);
    try {
      await persistAppLocale(locale);
      toast(t("settings.general.language.saved"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setLocaleSaving(false);
    }
  };

  useEffect(() => {
    setTimezone(appTimeZone);
  }, [appTimeZone]);

  useEffect(() => {
    if (!desktopPrefsAvailable) return;
    void getDesktopPrefs().then((prefs) => {
      setRunInBackground(prefs.run_in_background);
      setLaunchAtLogin(prefs.launch_at_login);
    });
  }, [desktopPrefsAvailable]);

  const saveTimezone = async () => {
    setTimezoneSaving(true);
    try {
      const next = await putTimezoneConfig({ timezone: timezone.trim() || "UTC" });
      setTimezone(next.timezone);
      await refreshAppTimeZone();
      toast(t("settings.general.timezone.saved", { tz: next.timezone }), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setTimezoneSaving(false);
    }
  };

  const saveDesktopPrefs = async () => {
    setDesktopPrefsSaving(true);
    try {
      const current = await getDesktopPrefs();
      const next = await setDesktopPrefs({
        run_in_background: runInBackground,
        launch_at_login: launchAtLogin,
        quick_chat_enabled: current.quick_chat_enabled,
        quick_chat_shortcut: current.quick_chat_shortcut,
        quick_chat_always_on_top: false,
      });
      setRunInBackground(next.run_in_background);
      setLaunchAtLogin(next.launch_at_login);
      toast(t("settings.general.desktopPrefsSaved"), "success");
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (isDesktopPrefsPartialSaveError(message)) {
        try {
          const next = await getDesktopPrefs();
          setRunInBackground(next.run_in_background);
          setLaunchAtLogin(next.launch_at_login);
        } catch {
          // 忽略回读失败
        }
        toast(t("settings.general.desktopPrefsAutostartFailed"), "info");
      } else {
        toast(message, "error");
      }
    } finally {
      setDesktopPrefsSaving(false);
    }
  };

  const downloadSettingsFile = (data: Record<string, unknown>) => {
    const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "settings.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await exportSettings();
      downloadSettingsFile(data);
      toast(t("settings.general.configExport.exported"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setExporting(false);
    }
  };

  const handleImportFile = async (file: File) => {
    let raw: unknown;
    try {
      raw = JSON.parse(await file.text());
    } catch {
      toast(t("settings.general.configImport.invalidJson"), "error");
      return;
    }
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      toast(t("settings.general.configImport.invalidFormat"), "error");
      return;
    }

    const firstConfirmed = await dialogs.confirm({
      title: t("settings.general.configImport.confirmTitle"),
      body: t("settings.general.configImport.confirmBody", { filename: file.name }),
      confirmText: t("settings.general.configImport.continueAction"),
      danger: true,
    });
    if (!firstConfirmed) return;

    const finalConfirmed = await dialogs.confirm({
      title: t("settings.general.configImport.finalConfirmTitle"),
      body: t("settings.general.configImport.finalConfirmBody"),
      confirmText: t("settings.general.configImport.confirmAction"),
      danger: true,
    });
    if (!finalConfirmed) return;

    setImporting(true);
    try {
      const next = await importSettings(raw as Record<string, unknown>);
      setTimezone(next.app.timezone);
      await refreshAppTimeZone();
      await persistAppLocale(next.app.locale === "en" ? "en" : "zh");
      if (isDesktopApp()) {
        await applyDesktopDevtoolsSettings();
      }
      toast(t("settings.general.configImport.imported"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setImporting(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-5">
      <SettingsSection
        title={t("settings.general.language.title")}
        description={t("settings.general.language.description")}
      >
        <Select
          value={appLocale}
          disabled={localeSaving}
          onChange={(e) => void changeLocale(e.target.value as AppLocale)}
          className="max-w-md"
        >
          {languageOptions.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </SettingsSection>

      <SettingsSection
        title={t("settings.general.theme.title")}
        description={t("settings.general.theme.description")}
      >
        <SegmentControl
          value={themePreference}
          onChange={setThemePreference}
          options={themeOptions}
          className="w-full max-w-md"
          optionClassName="flex-1 text-center"
        />
      </SettingsSection>

      {desktopPrefsAvailable && (
        <SettingsSection
          title={t("settings.general.menubar.title")}
          description={t("settings.general.menubar.description")}
        >
          <div className="grid max-w-xl gap-4">
            <label className="flex cursor-pointer items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={runInBackground}
                onChange={(e) => setRunInBackground(e.target.checked)}
              />
              <span>
                {t("settings.general.runInBackground.label")}
                <span className="mt-1 block text-xs text-muted-foreground">
                  {t("settings.general.runInBackground.hint")}
                </span>
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={launchAtLogin}
                onChange={(e) => setLaunchAtLogin(e.target.checked)}
              />
              <span>
                {t("settings.general.launchAtLogin.label")}
                <span className="mt-1 block text-xs text-muted-foreground">
                  {t("settings.general.launchAtLogin.hint")}
                </span>
              </span>
            </label>
            <div>
              <Button
                variant="primary"
                disabled={desktopPrefsSaving}
                onClick={() => void saveDesktopPrefs()}
              >
                {desktopPrefsSaving && <Loader2 className="size-4 animate-spin" />}
                {t("common.actions.save")}
              </Button>
            </div>
          </div>
        </SettingsSection>
      )}

      <SettingsSection title={t("settings.general.timezone.label")}>
        <div className="grid max-w-md gap-3">
          <div className="grid gap-1.5">
            <Label>{t("settings.general.timezone.label")}</Label>
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
              {t("common.actions.save")}
            </Button>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t("settings.general.configExport.title")}
        description={t("settings.general.configExport.description")}
      >
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={exporting || importing} onClick={() => void handleExport()}>
            {exporting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
            {t("common.actions.export")}
          </Button>
          <Button
            variant="secondary"
            disabled={exporting || importing}
            onClick={() => importInputRef.current?.click()}
          >
            {importing ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
            {t("settings.general.configImport.action")}
          </Button>
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleImportFile(file);
            }}
          />
        </div>
      </SettingsSection>
    </div>
  );
}
