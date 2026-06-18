import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/field";
import { cn } from "@/lib/utils";
import {
  formatGlobalShortcutForDisplay,
  keyboardEventToGlobalShortcut,
} from "@/lib/format-global-shortcut";

type ShortcutCaptureProps = {
  value: string;
  onChange: (shortcut: string) => void;
  disabled?: boolean;
};

export function ShortcutCapture({ value, onChange, disabled }: ShortcutCaptureProps) {
  const { t } = useTranslation();
  const [recording, setRecording] = useState(false);

  useEffect(() => {
    if (!recording) return;

    const onKeyDown = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();

      if (event.key === "Escape") {
        setRecording(false);
        return;
      }

      const next = keyboardEventToGlobalShortcut(event);
      if (!next) return;

      onChange(next);
      setRecording(false);
    };

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [onChange, recording]);

  return (
    <div className="grid gap-1.5">
      <Label>{t("settings.general.quickChat.shortcut.label")}</Label>
      <div className="flex max-w-md flex-wrap items-center gap-2">
        <div
          className={cn(
            "min-h-9 min-w-[12rem] flex-1 rounded-md border border-input bg-surface-2/60 px-3 py-2 font-mono text-sm",
            recording && "border-brand/60 ring-2 ring-ring",
            disabled && "opacity-50",
          )}
          aria-live="polite"
        >
          {recording ? t("settings.general.quickChat.shortcut.recording") : formatGlobalShortcutForDisplay(value)}
        </div>
        <Button
          type="button"
          variant={recording ? "secondary" : "outline"}
          disabled={disabled}
          onClick={() => setRecording((prev) => !prev)}
        >
          {recording ? t("settings.general.quickChat.shortcut.cancel") : t("settings.general.quickChat.shortcut.edit")}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t("settings.general.quickChat.shortcut.hint")}</p>
    </div>
  );
}
