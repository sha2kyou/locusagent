export async function openSessionInMainWindow(sessionId: string | null): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("desktop_open_session_in_main", { sessionId });
}
