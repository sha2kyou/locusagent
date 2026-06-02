/** 用量场景展示名（与 Agent/Host 上报的 scenario 一致） */
export const USAGE_SCENARIO_LABELS: Record<string, string> = {
  chat: "对话",
  compression: "上下文压缩",
  title_generation: "标题生成",
  curator: "记忆策展",
  skill_reflect: "技能反思",
  approval: "写入审查",
  tavily: "网络搜索",
  duckduckgo: "网络搜索",
  jina: "网页阅读",
  embedding: "向量嵌入",
  scheduled_run: "定时任务",
};

export function usageScenarioLabel(scenario: string): string {
  return USAGE_SCENARIO_LABELS[scenario] ?? scenario;
}

export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
