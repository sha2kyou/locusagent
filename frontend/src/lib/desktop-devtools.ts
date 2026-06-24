export async function applyDesktopDevtoolsSettings(): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("desktop_apply_devtools_settings");
}
