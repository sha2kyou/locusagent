import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { SegmentControl } from "@/components/ui/segment-control";
import { useToast } from "@/components/ui/toast";
import { useTheme, type ThemePreference } from "@/app/theme";
import { useRefreshAppTimezone, useAppTimezone } from "@/lib/use-app-timezone";
import { putTimezoneConfig } from "@/api/endpoints";
import { getDesktopPrefs, isDesktopPrefsAvailable, setDesktopPrefs } from "@/lib/desktop-prefs";
import { isDesktopPrefsPartialSaveError } from "@/lib/desktop-prefs-errors";
import { setAppLocale, SUPPORTED_LOCALES, type AppLocale } from "@/i18n";
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
  const { preference: themePreference, setPreference: setThemePreference } = useTheme();
  const appTimeZone = useAppTimezone();
  const refreshAppTimeZone = useRefreshAppTimezone();
  const [timezone, setTimezone] = useState("UTC");
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [runInBackground, setRunInBackground] = useState(false);
  const [launchAtLogin, setLaunchAtLogin] = useState(false);
  const [desktopPrefsSaving, setDesktopPrefsSaving] = useState(false);
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
      const next = await setDesktopPrefs({
        run_in_background: runInBackground,
        launch_at_login: launchAtLogin,
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

  return (
    <div className="space-y-5">
      <SettingsSection
        title={t("settings.general.language.title")}
        description={t("settings.general.language.description")}
      >
        <SegmentControl
          value={appLocale}
          onChange={(locale) => setAppLocale(locale as AppLocale)}
          options={languageOptions}
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
                {t("settings.general.saveDesktopPrefs")}
              </Button>
            </div>
          </div>
        </SettingsSection>
      )}

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
              {t("settings.general.timezone.save")}
            </Button>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
