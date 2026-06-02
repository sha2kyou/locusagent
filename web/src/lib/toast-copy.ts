const DEFAULT_MAX = 48;

export function truncateToastLabel(text: string, max = DEFAULT_MAX): string {
  const flat = text.trim().replace(/\s+/g, " ");
  if (!flat) return "（未命名）";
  if (flat.length <= max) return flat;
  return `${flat.slice(0, max - 1)}…`;
}

/** 例：已删除产物「线性代数公式」 */
export function toastAction(
  action: "已删除" | "已添加" | "已更新" | "已重连" | "已断开 OAuth",
  name: string,
  kind?: string,
): string {
  const label = truncateToastLabel(name);
  return kind ? `${action}${kind}「${label}」` : `${action}「${label}」`;
}
