import { isDesktopApp } from "@/lib/desktop-app";

export async function applyDesktopDevtoolsSettings(): Promise<void> {
  if (!isDesktopApp()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("desktop_apply_devtools_settings");
}
