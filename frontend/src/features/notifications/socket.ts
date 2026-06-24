import type { NotificationEntry } from "@/api/types";
import { getWorkspaceId } from "@/api/client";

export type NotificationWsEvent =
  | { type: "sync"; items: NotificationEntry[]; unread_count: number }
  | { type: "notification"; item: NotificationEntry; unread_count: number }
  | { type: "pong" };

export function notificationWsUrl(): string {
  const workspaceId = getWorkspaceId();
  const suffix = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  // 与 REST 同源（生产 :21223 托管 UI+API；开发经 Vite 代理 sidecar），保证 session Cookie 与 WS 鉴权一致。
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/notifications/ws${suffix}`;
}

export function parseNotificationWsEvent(raw: string): NotificationWsEvent | null {
  try {
    return JSON.parse(raw) as NotificationWsEvent;
  } catch {
    return null;
  }
}
