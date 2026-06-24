/** 服务端 Unix 秒（或已为 ms）→ UI startedAt（ms） */
export function toolStartedAtMs(raw: unknown): number {
  if (typeof raw !== "number" || !Number.isFinite(raw) || raw <= 0) return 0;
  return raw > 1e12 ? Math.round(raw) : Math.round(raw * 1000);
}
