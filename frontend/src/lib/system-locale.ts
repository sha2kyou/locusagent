import { isDesktopApp } from "./desktop-app.ts";

export type SystemLocaleTag = "zh" | "en";

/** 将 OS locale（如 zh-CN、en-US）映射为应用支持的语言 */
export function mapSystemLocale(tag: string): SystemLocaleTag {
  const lower = tag.trim().toLowerCase().replace(/_/g, "-");
  if (lower.startsWith("zh")) return "zh";
  return "en";
}

/** 桌面壳读取系统首选语言；Web 开发模式返回 null */
export async function getSystemLocale(): Promise<string | null> {
  if (!isDesktopApp()) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<string | null>("desktop_get_system_locale");
  } catch {
    return null;
  }
}
