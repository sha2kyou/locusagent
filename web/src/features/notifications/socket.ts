import type { NotificationEntry } from "@/api/types";

export type NotificationWsEvent =
  | { type: "sync"; items: NotificationEntry[]; unread_count: number }
  | { type: "notification"; item: NotificationEntry; unread_count: number }
  | { type: "pong" };

export function notificationWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/notifications/ws`;
}

export function parseNotificationWsEvent(raw: string): NotificationWsEvent | null {
  try {
    return JSON.parse(raw) as NotificationWsEvent;
  } catch {
    return null;
  }
}
