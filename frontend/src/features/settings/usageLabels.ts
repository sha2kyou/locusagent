import i18n from "../../i18n/index.ts";

function numberLocale(): string {
  return i18n.language === "en" ? "en-US" : "zh-CN";
}

/** 完整千分位（tooltip / 精确展示） */
export function formatTokenCountExact(n: number): string {
  if (!Number.isFinite(n)) return "0";
  return new Intl.NumberFormat(numberLocale()).format(Math.round(n));
}

/** 可读展示：中英文均用 K / M / B（与常见 Token 统计一致） */
export function formatTokenCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  const rounded = Math.round(n);
  if (rounded < 1000) return String(rounded);
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    compactDisplay: "short",
    maximumFractionDigits: rounded >= 1_000_000 ? 2 : 1,
  }).format(rounded);
}

export function formatTokenCountTitle(n: number): string | undefined {
  if (!Number.isFinite(n) || n < 1000) return undefined;
  return formatTokenCountExact(n);
}

/** 用量场景展示名（与 Agent/Host 上报的 scenario 一致） */
export function usageScenarioLabel(scenario: string): string {
  const key = `settings.usage.scenarios.${scenario}`;
  const translated = i18n.t(key);
  return translated === key ? scenario : translated;
}
