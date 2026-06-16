import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { getAppConfig, putAppConfig } from "@/api/endpoints";
import { stripWorkspacePrefix, withWorkspacePrefix } from "@/app/workspace-route";
import { applyDesktopDevtoolsSettings } from "@/lib/desktop-devtools";
import { isDesktopApp } from "@/lib/desktop-app";
import { SettingsSection } from "./SettingsSection";

export function SettingsDeveloperPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const location = useLocation();
  const { workspaceId } = stripWorkspacePrefix(location.pathname);
  const [devtoolsEnabled, setDevtoolsEnabled] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void getAppConfig().then((cfg) => {
      setDevtoolsEnabled(cfg.developer.devtools_enabled);
    });
  }, []);

  if (!isDesktopApp()) {
    return <Navigate to={withWorkspacePrefix("/settings/general", workspaceId)} replace />;
  }

  const save = async () => {
    setSaving(true);
    try {
      const next = await putAppConfig({ devtools_enabled: devtoolsEnabled });
      setDevtoolsEnabled(next.developer.devtools_enabled);
      await applyDesktopDevtoolsSettings();
      toast(t("settings.developer.saved"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <SettingsSection
        title={t("settings.developer.devtools.title")}
        description={t("settings.developer.devtools.description")}
      >
        <div className="grid max-w-xl gap-4">
          <label className="flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={devtoolsEnabled}
              onChange={(e) => setDevtoolsEnabled(e.target.checked)}
            />
            <span>
              {t("settings.developer.devtools.label")}
              <span className="mt-1 block text-xs text-muted-foreground">
                {t("settings.developer.devtools.hint")}
              </span>
            </span>
          </label>
          <p className="text-xs text-muted-foreground">{t("settings.developer.devtools.shortcutNote")}</p>
          <div>
            <Button variant="primary" disabled={saving} onClick={() => void save()}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              {t("settings.developer.save")}
            </Button>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
