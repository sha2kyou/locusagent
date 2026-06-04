const DESKTOP_GATEWAY_ORIGIN = "http://127.0.0.1:1420";
const OAUTH_LOGIN_URL = `${DESKTOP_GATEWAY_ORIGIN}/api/oauth/github/login?client=desktop`;

export function isDesktopApp(): boolean {
  if (typeof window === "undefined") return false;
  return window.location.origin === DESKTOP_GATEWAY_ORIGIN;
}

/** 桌面壳透明标题栏：供顶栏等区域拖拽移动窗口 */
export function desktopDragRegionProps(): Record<string, boolean> {
  return isDesktopApp() ? { "data-tauri-drag-region": true } : {};
}

export async function openDesktopOAuthLogin(): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    await invoke("open_oauth_login");
  } catch {
    // 兼容旧构建；新构建走显式 opener 权限
    await invoke("plugin:opener|open_url", { url: OAUTH_LOGIN_URL });
  }
}

export function desktopOAuthErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error) return error;
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return "无法打开系统浏览器";
}
