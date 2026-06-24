export interface DesktopPrefs {
  run_in_background: boolean;
  launch_at_login: boolean;
  quick_chat_enabled: boolean;
  quick_chat_shortcut: string;
  quick_chat_always_on_top: boolean;
  /** 运行时状态：当前快捷键是否已成功注册 */
  quick_chat_shortcut_registered?: boolean;
  /** 运行时状态：最近一次快捷键注册失败原因 */
  quick_chat_shortcut_error?: string | null;
}

export async function getDesktopPrefs(): Promise<DesktopPrefs> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<DesktopPrefs>("desktop_get_prefs");
}

export async function setDesktopPrefs(prefs: DesktopPrefs): Promise<DesktopPrefs> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<DesktopPrefs>("desktop_set_prefs", { prefs });
}
