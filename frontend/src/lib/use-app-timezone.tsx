import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getTimezoneConfig } from "@/api/endpoints";
import {
  formatDateTime,
  formatFull,
  formatMessageTime,
  formatRelative,
  resolveAppTimeZone,
  sessionListGroupLabel,
  toDatetimeLocalInTimeZone,
} from "@/lib/format-time";

type AppTimezoneContextValue = {
  timeZone: string;
  refreshTimeZone: () => Promise<void>;
};

const AppTimezoneContext = createContext<AppTimezoneContextValue | null>(null);

export function AppTimezoneProvider({ children }: { children: ReactNode }) {
  const [timeZone, setTimeZone] = useState("UTC");

  const refreshTimeZone = useCallback(async () => {
    try {
      const cfg = await getTimezoneConfig();
      setTimeZone(resolveAppTimeZone(cfg.timezone || "UTC"));
    } catch {
      setTimeZone("UTC");
    }
  }, []);

  useEffect(() => {
    void refreshTimeZone();
  }, [refreshTimeZone]);

  const value = useMemo(
    () => ({ timeZone, refreshTimeZone }),
    [timeZone, refreshTimeZone],
  );

  return <AppTimezoneContext.Provider value={value}>{children}</AppTimezoneContext.Provider>;
}

export function useAppTimezone(): string {
  const ctx = useContext(AppTimezoneContext);
  if (!ctx) throw new Error("useAppTimezone must be used within AppTimezoneProvider");
  return ctx.timeZone;
}

export function useRefreshAppTimezone(): () => Promise<void> {
  const ctx = useContext(AppTimezoneContext);
  if (!ctx) throw new Error("useRefreshAppTimezone must be used within AppTimezoneProvider");
  return ctx.refreshTimeZone;
}

export function useTimeFormatters() {
  const timeZone = useAppTimezone();
  return useMemo(
    () => ({
      timeZone,
      formatRelative: (iso: string) => formatRelative(iso, timeZone),
      formatFull: (iso: string) => formatFull(iso, timeZone),
      formatMessageTime: (iso: string) => formatMessageTime(iso, timeZone),
      formatDateTime: (iso: string | null | undefined) => formatDateTime(iso, timeZone),
      sessionListGroupLabel: (iso: string, now?: Date) => sessionListGroupLabel(iso, timeZone, now),
      toDatetimeLocal: (iso: string | null) => toDatetimeLocalInTimeZone(iso, timeZone),
    }),
    [timeZone],
  );
}
