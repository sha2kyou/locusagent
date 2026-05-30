import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  deleteNotification,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/api/endpoints";
import type { NotificationEntry } from "@/api/types";
import { useAuth } from "@/app/auth";
import { useToast } from "@/components/ui/toast";
import { notificationWsUrl, parseNotificationWsEvent } from "./socket";

interface NotificationContextValue {
  items: NotificationEntry[];
  unreadCount: number;
  loading: boolean;
  markRead: (id: number) => Promise<void>;
  markAllRead: () => Promise<void>;
  remove: (id: number) => Promise<void>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function useNotifications() {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationProvider");
  return ctx;
}

const WS_RETRY_MS = 3_000;
const WS_PING_MS = 25_000;

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  const toast = useToast();
  const [items, setItems] = useState<NotificationEntry[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const knownUnreadRef = useRef<number | null>(null);

  const notifyNew = useCallback(
    (count: number, item?: NotificationEntry) => {
      if (knownUnreadRef.current !== null && count > knownUnreadRef.current) {
        const delta = count - knownUnreadRef.current;
        if (item && delta === 1) {
          toast(item.title, item.kind === "error" ? "error" : item.kind === "success" ? "success" : "info");
        } else {
          toast(delta === 1 ? "你有 1 条新消息" : `你有 ${delta} 条新消息`, "info");
        }
      }
      knownUnreadRef.current = count;
    },
    [toast],
  );

  const applySync = useCallback((nextItems: NotificationEntry[], count: number) => {
    setItems(nextItems);
    setUnreadCount(count);
    knownUnreadRef.current = count;
    setLoading(false);
  }, []);

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

    const connect = () => {
      if (stopped) return;
      ws = new WebSocket(notificationWsUrl());

      ws.onmessage = (ev) => {
        const data = parseNotificationWsEvent(String(ev.data));
        if (!data) return;
        if (data.type === "sync") {
          applySync(data.items, data.unread_count);
        } else if (data.type === "notification") {
          applyPush(data.item, data.unread_count);
        }
      };

      ws.onclose = () => {
        if (!stopped) retryTimer = window.setTimeout(connect, WS_RETRY_MS);
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    pingTimer = window.setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
    }, WS_PING_MS);

    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      window.clearInterval(pingTimer);
      ws?.close();
    };
  }, [me, applySync, applyPush]);

  const markRead = useCallback(async (id: number) => {
    await markNotificationRead(id);
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, read: true } : i)));
    setUnreadCount((c) => {
      const next = Math.max(0, c - 1);
      knownUnreadRef.current = next;
      return next;
    });
  }, []);

  const markAllRead = useCallback(async () => {
    await markAllNotificationsRead();
    setItems((prev) => prev.map((i) => ({ ...i, read: true })));
    setUnreadCount(0);
    knownUnreadRef.current = 0;
  }, []);

  const remove = useCallback(async (id: number) => {
    await deleteNotification(id);
    setItems((prev) => {
      const removed = prev.find((i) => i.id === id);
      if (removed && !removed.read) {
        setUnreadCount((c) => {
          const next = Math.max(0, c - 1);
          knownUnreadRef.current = next;
          return next;
        });
      }
      return prev.filter((i) => i.id !== id);
    });
  }, []);

  return (
    <NotificationContext.Provider value={{ items, unreadCount, loading, markRead, markAllRead, remove }}>
      {children}
    </NotificationContext.Provider>
  );
}
