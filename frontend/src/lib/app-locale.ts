import { putLocaleConfig } from "@/api/endpoints";
import { applyAppLocale, normalizeAppLocale, type AppLocale } from "@/i18n";

const LOCALE_BROADCAST_CHANNEL = "locus-agent-app-locale";

let localeBroadcastChannel: BroadcastChannel | null = null;

function getLocaleBroadcastChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  localeBroadcastChannel ??= new BroadcastChannel(LOCALE_BROADCAST_CHANNEL);
  return localeBroadcastChannel;
}

/** 向其它 WebView（如快捷对话窗）广播语言变更。 */
export function broadcastAppLocale(locale: AppLocale): void {
  getLocaleBroadcastChannel()?.postMessage({ locale: normalizeAppLocale(locale) });
}

export function subscribeAppLocaleBroadcast(
  handler: (locale: AppLocale) => void,
): () => void {
  const channel = getLocaleBroadcastChannel();
  if (!channel) return () => {};

  const onMessage = (event: MessageEvent<{ locale?: string }>) => {
    const raw = event.data?.locale;
    if (raw !== "zh" && raw !== "en") return;
    handler(raw);
  };
  channel.addEventListener("message", onMessage);
  return () => channel.removeEventListener("message", onMessage);
}

export async function persistAppLocale(locale: AppLocale): Promise<void> {
  const normalized = normalizeAppLocale(locale);
  await putLocaleConfig({ locale: normalized });
  await applyAppLocale(normalized);
  broadcastAppLocale(normalized);
}
