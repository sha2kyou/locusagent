/** 工具调用参数 → 单行预览（用于头部截断展示） */
export function formatToolArgsPreview(raw: string | undefined | null): string | undefined {
  const text = String(raw ?? "").trim();
  if (!text || text === "{}") return undefined;
  try {
    const obj = JSON.parse(text) as unknown;
    if (obj && typeof obj === "object" && !Array.isArray(obj) && Object.keys(obj as object).length === 0) {
      return undefined;
    }
    return JSON.stringify(obj).replace(/\s+/g, " ");
  } catch {
    return text.replace(/\s+/g, " ");
  }
}
