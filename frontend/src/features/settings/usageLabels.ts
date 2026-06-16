import i18n from "../../i18n/index.ts";

export function formatTokenCount(n: number): string {
  return n.toLocaleString();
}

/** 用量场景展示名（与 Agent/Host 上报的 scenario 一致） */
export function usageScenarioLabel(scenario: string): string {
  const key = `settings.usage.scenarios.${scenario}`;
  const translated = i18n.t(key);
  return translated === key ? scenario : translated;
}
