import i18n from "../i18n/index.ts";

const TZ_PROBE_DATE = new Date("2020-01-01T00:00:00Z");

/** 校验 IANA 时区；无效时降级为 UTC */
export function resolveAppTimeZone(timeZone: string): string {
  const trimmed = String(timeZone || "").trim();
  if (!trimmed) return "UTC";
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: trimmed }).format(TZ_PROBE_DATE);
    return trimmed;
  } catch {
    return "UTC";
  }
}

/** 服务端 SQLite UTC 时间常无 Z，统一补全后再解析 */
export function normalizeIsoTimestamp(iso: string): string {
  return iso.includes("Z") || iso.includes("+") ? iso : `${iso}Z`;
}

function formatWithTimeZone(date: Date, timeZone: string, options: Intl.DateTimeFormatOptions): string {
  const tz = resolveAppTimeZone(timeZone);
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: tz }).format(date);
  } catch {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: "UTC" }).format(date);
  }
}

function calendarDateKeyFromDateEnCa(date: Date, timeZone: string): string {
  const tz = resolveAppTimeZone(timeZone);
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "UTC",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }
}

export function calendarDateKeyInTimeZone(iso: string, timeZone: string): string | null {
  const d = new Date(normalizeIsoTimestamp(iso));
  if (Number.isNaN(d.getTime())) return null;
  return calendarDateKeyFromDateEnCa(d, timeZone);
}

function daysBetweenDateKeys(earlierKey: string, laterKey: string): number {
  const a = Date.parse(`${earlierKey}T00:00:00Z`);
  const b = Date.parse(`${laterKey}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) return 999;
  return Math.round((b - a) / 86400000);
}

export type SessionListGroupKey = "today" | "yesterday" | "last7" | "last30" | "older";

export const SESSION_LIST_GROUP_ORDER: readonly SessionListGroupKey[] = [
  "today",
  "yesterday",
  "last7",
  "last30",
  "older",
];

export function sessionListGroupKey(
  iso: string,
  timeZone: string,
  now = new Date(),
): SessionListGroupKey {
  const tz = resolveAppTimeZone(timeZone);
  const sessionKey = calendarDateKeyInTimeZone(iso, tz);
  if (!sessionKey) return "older";
  const nowKey = calendarDateKeyFromDateEnCa(now, tz);
  const diffDays = daysBetweenDateKeys(sessionKey, nowKey);
  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return "last7";
  if (diffDays < 30) return "last30";
  return "older";
}

export function sessionListGroupLabel(
  iso: string,
  timeZone: string,
  now = new Date(),
): string {
  const key = sessionListGroupKey(iso, timeZone, now);
  return i18n.t(`time.sessionGroups.${key}`);
}

/** 相对时间：刚刚 / N 分钟前 / …，超出 30 天显示日期 */
export function formatRelative(iso: string, timeZone = "UTC"): string {
  const tz = resolveAppTimeZone(timeZone);
  const normalized = normalizeIsoTimestamp(iso);
  const t = new Date(normalized).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return i18n.t("time.relative.justNow");
  if (m < 60) return i18n.t("time.relative.minutesAgo", { count: m });
  const h = Math.floor(m / 60);
  if (h < 24) return i18n.t("time.relative.hoursAgo", { count: h });

  const sessionKey = calendarDateKeyInTimeZone(iso, tz);
  const nowKey = calendarDateKeyFromDateEnCa(new Date(), tz);
  if (sessionKey && nowKey) {
    const diffDays = daysBetweenDateKeys(sessionKey, nowKey);
    if (diffDays < 30) return i18n.t("time.relative.daysAgo", { count: diffDays });
  }

  return formatWithTimeZone(new Date(t), tz, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  });
}

/** 对话消息开始时间：当天仅时分，同年月日+时分，否则含年份 */
export function formatMessageTime(iso: string, timeZone = "UTC"): string {
  const tz = resolveAppTimeZone(timeZone);
  const d = new Date(normalizeIsoTimestamp(iso));
  if (Number.isNaN(d.getTime())) return iso;
  const now = new Date();
  const time = { hour: "2-digit", minute: "2-digit" } as const;
  const msgKey = calendarDateKeyFromDateEnCa(d, tz);
  const nowKey = calendarDateKeyFromDateEnCa(now, tz);
  if (msgKey === nowKey) {
    return formatWithTimeZone(d, tz, time);
  }
  const msgYear = formatWithTimeZone(d, tz, { year: "numeric" });
  const nowYear = formatWithTimeZone(now, tz, { year: "numeric" });
  if (msgYear === nowYear) {
    return formatWithTimeZone(d, tz, { month: "numeric", day: "numeric", ...time });
  }
  return formatWithTimeZone(d, tz, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    ...time,
  });
}

/** 绝对时间 */
export function formatFull(iso: string, timeZone = "UTC"): string {
  const d = new Date(normalizeIsoTimestamp(iso));
  if (Number.isNaN(d.getTime())) return iso;
  return formatWithTimeZone(d, timeZone, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** 日期 + 时分（定时任务等列表） */
export function formatDateTime(iso: string | null | undefined, timeZone = "UTC"): string {
  if (!iso) return "—";
  const d = new Date(normalizeIsoTimestamp(iso));
  if (Number.isNaN(d.getTime())) return iso;
  return formatWithTimeZone(d, timeZone, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** ISO 时间转为 `<input type="datetime-local">` 值（按用户时区） */
export function toDatetimeLocalInTimeZone(iso: string | null, timeZone = "UTC"): string {
  if (!iso) return "";
  const d = new Date(normalizeIsoTimestamp(iso));
  if (Number.isNaN(d.getTime())) return "";
  const tz = resolveAppTimeZone(timeZone);
  try {
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const parts = fmt.formatToParts(d);
    const get = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((p) => p.type === type)?.value ?? "00";
    return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
  } catch {
    return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}T${pad2(
      d.getUTCHours(),
    )}:${pad2(d.getUTCMinutes())}`;
  }
}
