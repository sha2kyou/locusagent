import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { getAppConfig, putAppConfig } from "@/api/endpoints";
import type { AppConfigUpdate } from "@/api/types";
import { SettingsSection } from "./SettingsSection";

export function SettingsToolsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const [enableTerminal, setEnableTerminal] = useState(false);
  const [whitelist, setWhitelist] = useState("git,npm,node,python3,make");
  const [denylist, setDenylist] = useState("sh,bash,zsh,dash,fish");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void getAppConfig().then((cfg) => {
      setEnableTerminal(cfg.terminal.enable_terminal);
      setWhitelist(cfg.terminal.whitelist);
      setDenylist(cfg.terminal.denylist || "sh,bash,zsh,dash,fish");
    });
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const body: AppConfigUpdate = {
        enable_terminal: enableTerminal,
        terminal_whitelist: whitelist,
        terminal_denylist: denylist,
      };
      const next = await putAppConfig(body);
      setEnableTerminal(next.terminal.enable_terminal);
      setWhitelist(next.terminal.whitelist);
      setDenylist(next.terminal.denylist);
      toast(t("settings.tools.saved"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <SettingsSection
        title={t("settings.tools.terminal.title")}
        description={t("settings.tools.terminal.description")}
      >
        <div className="grid max-w-xl gap-4">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enableTerminal}
              onChange={(e) => setEnableTerminal(e.target.checked)}
            />
            {t("settings.tools.enableTerminal")}
          </label>

          <div className="grid gap-1.5">
            <Label>
              {t("settings.tools.whitelist.label")}（TERMINAL_WHITELIST）
            </Label>
            <Input
              value={whitelist}
              onChange={(e) => setWhitelist(e.target.value)}
              placeholder="git,npm,node,python3,make"
            />
            <p className="text-xs text-muted-foreground">{t("settings.tools.whitelist.detail")}</p>
          </div>

          <div className="grid gap-1.5">
            <Label>
              {t("settings.tools.denylist.label")}（TERMINAL_DENYLIST）
            </Label>
            <Input
              value={denylist}
              onChange={(e) => setDenylist(e.target.value)}
              placeholder="sh,bash,zsh,dash,fish"
            />
            <p className="text-xs text-muted-foreground">{t("settings.tools.denylist.detail")}</p>
          </div>

          <div>
            <Button variant="primary" disabled={saving} onClick={() => void save()}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              {t("common.actions.save")}
            </Button>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
