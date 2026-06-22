import { useEffect, type ReactNode } from "react";
import {
  applyAppLocale,
  consumeLegacyLocalStorageLocale,
  ensureI18nReady,
  normalizeAppLocale,
} from "@/i18n";
import { getLocaleConfig, putLocaleConfig } from "@/api/endpoints";
import { subscribeAppLocaleBroadcast } from "@/lib/app-locale";

/** 登录后从 settings.json 同步界面语言，并迁移旧版 localStorage 偏好。 */
export function AppLocaleProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    void (async () => {
      await ensureI18nReady();
      try {
        const cfg = await getLocaleConfig();
        await applyAppLocale(normalizeAppLocale(cfg.locale));
        return;
      } catch {
        // 回退：迁移 localStorage 中的旧偏好
      }

      const legacy = consumeLegacyLocalStorageLocale();
      if (!legacy) return;

      try {
        await putLocaleConfig({ locale: legacy });
      } catch {
        // 离线或尚未就绪时仍应用本地语言
      }
      await applyAppLocale(legacy);
    })();
  }, []);

  useEffect(() => {
    return subscribeAppLocaleBroadcast((locale) => {
      void applyAppLocale(locale);
    });
  }, []);

  return children;
}
