import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zh from "./locales/zh.json" with { type: "json" };
import en from "./locales/en.json" with { type: "json" };
import { getSystemLocale, mapSystemLocale } from "../lib/system-locale.ts";

/** @deprecated migrated to settings.json; read once for legacy installs */
export const LOCALE_STORAGE_KEY = "apod-locale";

export type AppLocale = "zh" | "en";

export const SUPPORTED_LOCALES: readonly AppLocale[] = ["zh", "en"];

/** 无 settings 记录、且无法读取系统语言时的默认语言 */
export const DEFAULT_LOCALE: AppLocale = "en";

export function normalizeAppLocale(locale: string): AppLocale {
  return locale.trim().toLowerCase() === "en" ? "en" : "zh";
}

/** 同步 `<html lang>`，避免与界面语言不一致时触发 WebKit 中文智能标点。 */
export function syncDocumentLang(locale: AppLocale): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
}

export function consumeLegacyLocalStorageLocale(): AppLocale | null {
  if (typeof localStorage === "undefined") return null;
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored !== "zh" && stored !== "en") return null;
  localStorage.removeItem(LOCALE_STORAGE_KEY);
  return stored;
}

async function resolveBootstrapLocale(): Promise<AppLocale> {
  const system = await getSystemLocale();
  if (system) return mapSystemLocale(system);
  return DEFAULT_LOCALE;
}

let initPromise: Promise<void> | null = null;

export async function ensureI18nReady(): Promise<void> {
  if (i18n.isInitialized) return;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    const lng = await resolveBootstrapLocale();
    await i18n.use(initReactI18next).init({
      resources: {
        zh: { translation: zh },
        en: { translation: en },
      },
      lng,
      fallbackLng: { default: [DEFAULT_LOCALE, "zh"] },
      interpolation: { escapeValue: false },
    });
    syncDocumentLang(normalizeAppLocale(lng));
  })();

  return initPromise;
}

export async function applyAppLocale(locale: AppLocale): Promise<void> {
  await ensureI18nReady();
  const normalized = normalizeAppLocale(locale);
  if (i18n.language !== normalized) {
    await i18n.changeLanguage(normalized);
  }
  syncDocumentLang(normalized);
}

export function getAppLocale(): AppLocale {
  return normalizeAppLocale(i18n.language || DEFAULT_LOCALE);
}

export default i18n;
