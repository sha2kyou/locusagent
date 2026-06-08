import type { NotificationEntry } from "@/api/types";
import { isDesktopApp } from "@/lib/desktop-app";

async function invokeNotify(options: { title: string; body?: string; id?: number }): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("plugin:notification|notify", {
    options: {
      id: options.id,
      title: options.title,
      body: options.body,
      autoCancel: true,
    },
  });
}

/** 将通知中心条目镜像到 macOS 系统通知（不影响应用内 toast）。 */
export function mirrorNotificationEntryToSystem(item: NotificationEntry): void {
  if (!isDesktopApp()) return;
  const title = item.title.trim();
  if (!title) return;
  void invokeNotify({
    id: item.id,
    title,
    body: item.body?.trim() || undefined,
  }).catch(() => {
    /* 系统通知失败时不阻断 toast / 铃铛 */
  });
}

export function mirrorNotificationSummaryToSystem(delta: number): void {
  if (!isDesktopApp()) return;
  void invokeNotify({
    title: delta === 1 ? "你有 1 条新消息" : `你有 ${delta} 条新消息`,
  }).catch(() => {});
}
