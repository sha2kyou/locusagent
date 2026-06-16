import { putLocaleConfig } from "@/api/endpoints";
import { applyAppLocale, normalizeAppLocale, type AppLocale } from "@/i18n";

export async function persistAppLocale(locale: AppLocale): Promise<void> {
  const normalized = normalizeAppLocale(locale);
  await putLocaleConfig({ locale: normalized });
  await applyAppLocale(normalized);
}
