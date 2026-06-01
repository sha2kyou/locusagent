import type { NotificationEntry } from "@/api/types";
import { getWorkspaceId } from "@/api/client";

export type NotificationWsEvent =
  | { type: "sync"; items: NotificationEntry[]; unread_count: number }
  | { type: "notification"; item: NotificationEntry; unread_count: number }
  | { type: "pong" };

export function notificationWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const workspaceId = getWorkspaceId();
  const suffix = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  return `${proto}//${window.location.host}/api/notifications/ws${suffix}`;
}

export function parseNotificationWsEvent(raw: string): NotificationWsEvent | null {
  try {
    return JSON.parse(raw) as NotificationWsEvent;
  } catch {
    return null;
  }
}
