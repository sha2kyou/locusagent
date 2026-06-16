import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/api/endpoints";
import type { NotificationEntry } from "@/api/types";
import { useAuth } from "@/app/auth";
import { stripWorkspacePrefix } from "@/app/workspace-route";
import { useToast } from "@/components/ui/toast";
import {
  mirrorNotificationEntryToSystem,
  mirrorNotificationSummaryToSystem,
} from "@/lib/desktop-notification";
import { toastMessageForNotification } from "./notification-copy";
import { notificationWsUrl, parseNotificationWsEvent } from "./socket";

interface NotificationContextValue {
  items: NotificationEntry[];
  unreadCount: number;
  loading: boolean;
  markRead: (id: number) => Promise<void>;
  markAllRead: () => Promise<void>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function useNotifications() {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationProvider");
  return ctx;
}

const WS_RETRY_MS = 3_000;
const WS_PING_MS = 25_000;
const WS_AUTH_CLOSE_CODE = 4401;

function toastTypeFromKind(kind: NotificationEntry["kind"]): "info" | "success" | "error" {
  if (kind === "error") return "error";
  if (kind === "success") return "success";
  return "info";
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { me } = useAuth();
  const location = useLocation();
  const toast = useToast();
  const [items, setItems] = useState<NotificationEntry[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const knownUnreadRef = useRef<number | null>(null);

  const workspaceKey =
    stripWorkspacePrefix(location.pathname).workspaceId ?? me?.current_workspace_id ?? "";

  const notifyNew = useCallback(
    (count: number, item?: NotificationEntry) => {
      if (item) {
        toast(toastMessageForNotification(item), toastTypeFromKind(item.kind), { sticky: true });
        mirrorNotificationEntryToSystem(item);
      } else if (knownUnreadRef.current !== null && count > knownUnreadRef.current) {
        const delta = count - knownUnreadRef.current;
        toast(delta === 1 ? t("notifications.newMessage") : t("notifications.newMessages", { count: delta }), "info", { sticky: true });
        mirrorNotificationSummaryToSystem(delta);
      }
      knownUnreadRef.current = count;
    },
    [toast, t],
  );

  const applySync = useCallback(
    (nextItems: NotificationEntry[], count: number) => {
      const unreadItems = nextItems.filter((i) => !i.read);
      const prev = knownUnreadRef.current;
      if (prev !== null && count > prev) {
        const delta = count - prev;
        if (delta === 1 && unreadItems[0]) {
          toast(
            toastMessageForNotification(unreadItems[0]),
            toastTypeFromKind(unreadItems[0].kind),
            { sticky: true },
          );
          mirrorNotificationEntryToSystem(unreadItems[0]);
        } else {
          toast(delta === 1 ? t("notifications.newMessage") : t("notifications.newMessages", { count: delta }), "info", { sticky: true });
          mirrorNotificationSummaryToSystem(delta);
        }
      }
      setItems(unreadItems);
      setUnreadCount(count);
      knownUnreadRef.current = count;
      setLoading(false);
    },
    [toast, t],
  );

  const applyPush = useCallback(
    (item: NotificationEntry, count: number) => {
      setItems((prev) => {
        if (prev.some((i) => i.id === item.id)) return prev;
        return [item, ...prev].slice(0, 50);
      });
      setUnreadCount(count);
      notifyNew(count, item);
    },
    [notifyNew],
  );

  const applySyncRef = useRef(applySync);
  const applyPushRef = useRef(applyPush);
  applySyncRef.current = applySync;
  applyPushRef.current = applyPush;

  useEffect(() => {
    if (!me) {
      setItems([]);
      setUnreadCount(0);
      setLoading(false);
      knownUnreadRef.current = null;
      return;
    }
    knownUnreadRef.current = null;
    setLoading(true);
  }, [me]);

  useEffect(() => {
    if (!me) return;

    let ws: WebSocket | null = null;
    let retryTimer = 0;
    let pingTimer = 0;
    let stopped = false;
    let generation = 0;

    const connect = () => {
      if (stopped) return;
      const gen = ++generation;
      const socket = new WebSocket(notificationWsUrl());
      ws = socket;

      socket.onmessage = (ev) => {
        if (gen !== generation) return;
        const data = parseNotificationWsEvent(String(ev.data));
        if (!data) return;
        if (data.type === "sync") {
          applySyncRef.current(data.items, data.unread_count);
        } else if (data.type === "notification") {
          applyPushRef.current(data.item, data.unread_count);
        }
      };

      socket.onclose = (ev) => {
        if (stopped || gen !== generation) return;
        if (ev.code === WS_AUTH_CLOSE_CODE) return;
        retryTimer = window.setTimeout(connect, WS_RETRY_MS);
      };
    };

    void listNotifications()
      .then((data) => {
        if (stopped) return;
        applySyncRef.current(data.items, data.unread_count);
        connect();
      })
      .catch(() => {
        if (!stopped) setLoading(false);
      });

    pingTimer = window.setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
    }, WS_PING_MS);

    return () => {
      stopped = true;
      generation += 1;
      window.clearTimeout(retryTimer);
      window.clearInterval(pingTimer);
      if (ws) {
        ws.onclose = null;
        ws.close();
        ws = null;
      }
    };
  }, [me, workspaceKey]);

  const markRead = useCallback(async (id: number) => {
    await markNotificationRead(id);
    setItems((prev) => {
      if (!prev.some((i) => i.id === id)) return prev;
      setUnreadCount((c) => {
        const next = Math.max(0, c - 1);
        knownUnreadRef.current = next;
        return next;
      });
      return prev.filter((i) => i.id !== id);
    });
  }, []);

  const markAllRead = useCallback(async () => {
    await markAllNotificationsRead();
    setItems([]);
    setUnreadCount(0);
    knownUnreadRef.current = 0;
  }, []);

  return (
    <NotificationContext.Provider value={{ items, unreadCount, loading, markRead, markAllRead }}>
      {children}
    </NotificationContext.Provider>
  );
};
