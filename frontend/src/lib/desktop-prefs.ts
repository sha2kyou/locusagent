import { isDesktopApp } from "@/lib/desktop-app";

export interface DesktopPrefs {
  run_in_background: boolean;
  launch_at_login: boolean;
}

export async function getDesktopPrefs(): Promise<DesktopPrefs> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<DesktopPrefs>("desktop_get_prefs");
}

export async function setDesktopPrefs(prefs: DesktopPrefs): Promise<DesktopPrefs> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<DesktopPrefs>("desktop_set_prefs", { prefs });
}

export function isDesktopPrefsAvailable(): boolean {
  return isDesktopApp();
}
