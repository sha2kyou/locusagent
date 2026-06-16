import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zh from "./locales/zh.json" with { type: "json" };
import en from "./locales/en.json" with { type: "json" };
import { getSystemLocale, mapSystemLocale } from "../lib/system-locale.ts";

export const LOCALE_STORAGE_KEY = "apod-locale";

export type AppLocale = "zh" | "en";

export const SUPPORTED_LOCALES: readonly AppLocale[] = ["zh", "en"];

/** 无用户偏好、且无法读取系统语言时的默认语言 */
export const DEFAULT_LOCALE: AppLocale = "en";

function readStoredLocale(): AppLocale | null {
  if (typeof localStorage === "undefined") return null;
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored === "zh" || stored === "en") return stored;
  return null;
}

async function resolveInitialLocale(): Promise<AppLocale> {
  const stored = readStoredLocale();
  if (stored) return stored;

  const system = await getSystemLocale();
  if (system) return mapSystemLocale(system);

  return DEFAULT_LOCALE;
}

let initPromise: Promise<void> | null = null;

export async function ensureI18nReady(): Promise<void> {
  if (i18n.isInitialized) return;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    const lng = await resolveInitialLocale();
    await i18n.use(initReactI18next).init({
      resources: {
        zh: { translation: zh },
        en: { translation: en },
      },
      lng,
      fallbackLng: { default: [DEFAULT_LOCALE, "zh"] },
      interpolation: { escapeValue: false },
    });
  })();

  return initPromise;
}

export function setAppLocale(locale: AppLocale): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }
  void i18n.changeLanguage(locale);
}

export function getAppLocale(): AppLocale {
  const lng = i18n.language;
  return lng === "en" ? "en" : "zh";
}

export default i18n;
