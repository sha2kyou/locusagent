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

/** 对话消息开始时间：当天仅时分，同年月日+时分，否则含年份 */
export function formatMessageTime(iso: string): string {
  const normalized = iso.includes("Z") || iso.includes("+") ? iso : `${iso}Z`;
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return iso;
  const now = new Date();
  const time = { hour: "2-digit", minute: "2-digit" } as const;
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString(undefined, time);
  }
  if (d.getFullYear() === now.getFullYear()) {
    return d.toLocaleString(undefined, { month: "numeric", day: "numeric", ...time });
  }
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    ...time,
  });
}

/** 绝对时间（本地格式） */
export function formatFull(iso: string): string {
  const normalized = iso.includes("Z") || iso.includes("+") ? iso : iso + "Z";
  const t = new Date(normalized).getTime();
  if (Number.isNaN(t)) return iso;
  return new Date(t).toLocaleString();
}
