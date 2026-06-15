import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { getAppConfig, putAppConfig } from "@/api/endpoints";
import type { AppConfigUpdate } from "@/api/types";
import { SettingsSection } from "./SettingsSection";

export function SettingsToolsPage() {
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
      toast("Terminal 设置已保存", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <SettingsSection
        title="Terminal"
        description="控制 Agent 是否可执行 shell 命令，以及允许/禁止的可执行文件名（逗号分隔，不含路径）。"
      >
        <div className="grid max-w-xl gap-4">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enableTerminal}
              onChange={(e) => setEnableTerminal(e.target.checked)}
            />
            启用 terminal 工具
          </label>

          <div className="grid gap-1.5">
            <Label>白名单（TERMINAL_WHITELIST）</Label>
            <Input
              value={whitelist}
              onChange={(e) => setWhitelist(e.target.value)}
              placeholder="git,npm,node,python3,make"
            />
            <p className="text-xs text-muted-foreground">
              仅允许 bare 命令名（如 git、npm），不允许路径；为空时拒绝所有命令。
            </p>
          </div>

          <div className="grid gap-1.5">
            <Label>禁止项（TERMINAL_DENYLIST）</Label>
            <Input
              value={denylist}
              onChange={(e) => setDenylist(e.target.value)}
              placeholder="sh,bash,zsh,dash,fish"
            />
            <p className="text-xs text-muted-foreground">
              即使在白名单中，命中禁止项的命令也会被拦截。
            </p>
          </div>

          <div>
            <Button variant="primary" disabled={saving} onClick={() => void save()}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              保存
            </Button>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
