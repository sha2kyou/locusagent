import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { SegmentControl } from "@/components/ui/segment-control";
import { useToast } from "@/components/ui/toast";
import { useTheme, type ThemePreference } from "@/app/theme";
import { getTimezoneConfig, putTimezoneConfig } from "@/api/endpoints";
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
  const [timezone, setTimezone] = useState("UTC");
  const [timezoneSaving, setTimezoneSaving] = useState(false);

  useEffect(() => {
    void getTimezoneConfig().then((tz) => {
      setTimezone(tz.timezone || "UTC");
    });
  }, []);

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
    <div className="space-y-5">
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
