import type { TFunction } from "i18next";

/** 与后端 persistence / session_title 一致的默认会话标题 */
export const BACKEND_DEFAULT_SESSION_TITLE = "新对话";

export function isBackendDefaultSessionTitle(title: string | null | undefined): boolean {
  const trimmed = (title ?? "").trim();
  return !trimmed || trimmed === BACKEND_DEFAULT_SESSION_TITLE;
}

export function displaySessionTitle(title: string, t: TFunction): string {
  if (isBackendDefaultSessionTitle(title)) {
    return t("chat.session.defaultTitle");
  }
  return title.trim();
}
