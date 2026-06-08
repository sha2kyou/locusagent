import type { NotificationEntry } from "@/api/types";
import { getWorkspaceId } from "@/api/client";
import { DESKTOP_API_ORIGIN, isDesktopApp } from "@/lib/desktop-app";

export type NotificationWsEvent =
  | { type: "sync"; items: NotificationEntry[]; unread_count: number }
  | { type: "notification"; item: NotificationEntry; unread_count: number }
  | { type: "pong" };

export function notificationWsUrl(): string {
  const workspaceId = getWorkspaceId();
  const suffix = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  // 桌面端 WS 绕过本地 gateway 二次握手（易断连）；Cookie 按 host 共享，1223 仍可鉴权。
  const base = isDesktopApp() ? DESKTOP_API_ORIGIN : window.location.origin;
  const proto = base.startsWith("https:") ? "wss:" : "ws:";
  const host = new URL(base).host;
  return `${proto}//${host}/api/notifications/ws${suffix}`;
}

export function parseNotificationWsEvent(raw: string): NotificationWsEvent | null {
  try {
    return JSON.parse(raw) as NotificationWsEvent;
  } catch {
    return null;
  }
}
