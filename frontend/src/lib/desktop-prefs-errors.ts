/** 桌面偏好已写入磁盘，但开机自启同步失败（Rust 端固定中文前缀） */
const DESKTOP_PREFS_PARTIAL_SAVE_PREFIX = "偏好已保存";

export function isDesktopPrefsPartialSaveError(message: string): boolean {
  return message.includes(DESKTOP_PREFS_PARTIAL_SAVE_PREFIX);
}
