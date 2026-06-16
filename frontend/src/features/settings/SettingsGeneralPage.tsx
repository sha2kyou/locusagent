import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { SegmentControl } from "@/components/ui/segment-control";
import { useToast } from "@/components/ui/toast";
import { useTheme, type ThemePreference } from "@/app/theme";
import { useRefreshAppTimezone, useAppTimezone } from "@/lib/use-app-timezone";
import { putTimezoneConfig } from "@/api/endpoints";
import { getDesktopPrefs, isDesktopPrefsAvailable, setDesktopPrefs } from "@/lib/desktop-prefs";
import { SettingsSection } from "./SettingsSection";

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

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
      toast(`时区已保存：${next.timezone}`, "success");
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
      toast("桌面偏好已保存", "success");
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (message.includes("偏好已保存")) {
        try {
          const next = await getDesktopPrefs();
          setRunInBackground(next.run_in_background);
          setLaunchAtLogin(next.launch_at_login);
        } catch {
          // 忽略回读失败
        }
        toast(message, "info");
      } else {
        toast(message, "error");
      }
    } finally {
      setDesktopPrefsSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      {desktopPrefsAvailable && (
        <SettingsSection
          title="菜单栏与后台"
          description="关闭窗口后可在菜单栏保留 AgentPod；开机自启需在此手动开启。"
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
                关闭窗口后在菜单栏继续运行
                <span className="mt-1 block text-xs text-muted-foreground">
                  点击窗口关闭按钮时隐藏窗口，不退出应用；可从菜单栏图标重新打开。
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
                登录时自动启动 AgentPod
                <span className="mt-1 block text-xs text-muted-foreground">
                  在系统登录时启动应用；默认关闭，需手动开启。
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
                保存桌面偏好
              </Button>
            </div>
          </div>
        </SettingsSection>
      )}

      <SettingsSection title="主题" description="界面配色方案，立即生效。">
        <SegmentControl
          value={themePreference}
          onChange={setThemePreference}
          options={THEME_OPTIONS}
          className="w-full max-w-md"
          optionClassName="flex-1 text-center"
        />
      </SettingsSection>

      <SettingsSection title="时区">
        <div className="grid max-w-md gap-3">
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
      </SettingsSection>
    </div>
  );
}
