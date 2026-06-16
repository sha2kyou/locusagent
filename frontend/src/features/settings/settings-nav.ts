import { BarChart3, Cpu, ScrollText, Settings2, Terminal } from "lucide-react";

export const SETTINGS_NAV = [
  { to: "general", labelKey: "settings.nav.general.label", descriptionKey: "settings.nav.general.description", icon: Settings2 },
  { to: "models", labelKey: "settings.nav.models.label", descriptionKey: "settings.nav.models.description", icon: Cpu },
  { to: "tools", labelKey: "settings.nav.tools.label", descriptionKey: "settings.nav.tools.description", icon: Terminal },
  { to: "usage", labelKey: "settings.nav.usage.label", descriptionKey: "settings.nav.usage.description", icon: BarChart3 },
  { to: "logs", labelKey: "settings.nav.logs.label", descriptionKey: "settings.nav.logs.description", icon: ScrollText },
] as const;

export type SettingsNavId = (typeof SETTINGS_NAV)[number]["to"];

export const SETTINGS_PAGE_META: Record<SettingsNavId, { titleKey: string; subtitleKey: string }> = {
  general: { titleKey: "settings.pages.general.title", subtitleKey: "settings.pages.general.subtitle" },
  models: { titleKey: "settings.pages.models.title", subtitleKey: "settings.pages.models.subtitle" },
  tools: { titleKey: "settings.pages.tools.title", subtitleKey: "settings.pages.tools.subtitle" },
  usage: { titleKey: "settings.pages.usage.title", subtitleKey: "settings.pages.usage.subtitle" },
  logs: { titleKey: "settings.pages.logs.title", subtitleKey: "settings.pages.logs.subtitle" },
};
