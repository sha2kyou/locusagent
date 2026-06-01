/** 相对时间：刚刚 / N 分钟前 / …，超出 30 天显示日期 */
export function formatRelative(iso: string): string {
  const normalized = iso.includes("Z") || iso.includes("+") ? iso : iso + "Z";
  const t = new Date(normalized).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return new Date(t).toLocaleDateString();
}

/** 绝对时间（本地格式） */
export function formatFull(iso: string): string {
  const normalized = iso.includes("Z") || iso.includes("+") ? iso : iso + "Z";
  const t = new Date(normalized).getTime();
  if (Number.isNaN(t)) return iso;
  return new Date(t).toLocaleString();
}
