import type { TFunction } from "i18next";

/** Stored defaults from backend (zh/en); must stay in sync with locus_shared.session_titles */
export const BACKEND_DEFAULT_SESSION_TITLES = ["新对话", "New chat"] as const;

/** @deprecated use BACKEND_DEFAULT_SESSION_TITLES */
export const BACKEND_DEFAULT_SESSION_TITLE = BACKEND_DEFAULT_SESSION_TITLES[0];

const DEFAULT_TITLE_SET = new Set<string>(BACKEND_DEFAULT_SESSION_TITLES);

export function isBackendDefaultSessionTitle(title: string | null | undefined): boolean {
  const trimmed = (title ?? "").trim();
  return !trimmed || DEFAULT_TITLE_SET.has(trimmed);
}

export function displaySessionTitle(title: string, t: TFunction): string {
  if (isBackendDefaultSessionTitle(title)) {
    return t("chat.session.defaultTitle");
  }
  return title.trim();
}
