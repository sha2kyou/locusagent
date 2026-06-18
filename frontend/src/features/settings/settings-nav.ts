import { BarChart3, Binary, Code2, Cpu, MessageSquarePlus, ScrollText, Settings2, Terminal } from "lucide-react";
import { isDesktopApp } from "@/lib/desktop-app";

export const SETTINGS_NAV_EMBEDDING = {
  to: "embedding",
  labelKey: "settings.nav.embedding.label",
  descriptionKey: "settings.nav.embedding.description",
  icon: Binary,
} as const;

export const SETTINGS_NAV_BASE = [
  { to: "general", labelKey: "settings.nav.general.label", descriptionKey: "settings.nav.general.description", icon: Settings2 },
  { to: "models", labelKey: "settings.nav.models.label", descriptionKey: "settings.nav.models.description", icon: Cpu },
  SETTINGS_NAV_EMBEDDING,
  { to: "tools", labelKey: "settings.nav.tools.label", descriptionKey: "settings.nav.tools.description", icon: Terminal },
  { to: "usage", labelKey: "settings.nav.usage.label", descriptionKey: "settings.nav.usage.description", icon: BarChart3 },
  { to: "logs", labelKey: "settings.nav.logs.label", descriptionKey: "settings.nav.logs.description", icon: ScrollText },
] as const;

export const SETTINGS_NAV_QUICK_CHAT = {
  to: "quick-chat",
  labelKey: "settings.nav.quickChat.label",
  descriptionKey: "settings.nav.quickChat.description",
  icon: MessageSquarePlus,
} as const;

export const SETTINGS_NAV_DEVELOPER = {
  to: "developer",
  labelKey: "settings.nav.developer.label",
  descriptionKey: "settings.nav.developer.description",
  icon: Code2,
} as const;

export type SettingsNavId =
  | (typeof SETTINGS_NAV_BASE)[number]["to"]
  | typeof SETTINGS_NAV_QUICK_CHAT.to
  | typeof SETTINGS_NAV_DEVELOPER.to;

export function getSettingsNav() {
  if (isDesktopApp()) {
    return [
      SETTINGS_NAV_BASE[0],
      SETTINGS_NAV_QUICK_CHAT,
      ...SETTINGS_NAV_BASE.slice(1),
      SETTINGS_NAV_DEVELOPER,
    ];
  }
  return [...SETTINGS_NAV_BASE];
}

export const SETTINGS_PAGE_META: Record<SettingsNavId, { titleKey: string; subtitleKey: string }> = {
  general: { titleKey: "settings.pages.general.title", subtitleKey: "settings.pages.general.subtitle" },
  models: { titleKey: "settings.pages.models.title", subtitleKey: "settings.pages.models.subtitle" },
  embedding: {
    titleKey: "settings.pages.embedding.title",
    subtitleKey: "settings.pages.embedding.subtitle",
  },
  tools: { titleKey: "settings.pages.tools.title", subtitleKey: "settings.pages.tools.subtitle" },
  usage: { titleKey: "settings.pages.usage.title", subtitleKey: "settings.pages.usage.subtitle" },
  logs: { titleKey: "settings.pages.logs.title", subtitleKey: "settings.pages.logs.subtitle" },
  "quick-chat": {
    titleKey: "settings.pages.quickChat.title",
    subtitleKey: "settings.pages.quickChat.subtitle",
  },
  developer: {
    titleKey: "settings.pages.developer.title",
    subtitleKey: "settings.pages.developer.subtitle",
  },
};

/** @deprecated use getSettingsNav() */
export const SETTINGS_NAV = SETTINGS_NAV_BASE;
