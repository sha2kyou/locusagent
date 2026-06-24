import type { NotificationEntry } from "@/api/types";
import i18n from "../i18n/index.ts";

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

/** 将通知中心条目镜像到系统通知（不影响应用内 toast）。 */
export function mirrorNotificationEntryToSystem(item: NotificationEntry): void {
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
  void invokeNotify({
    title: delta === 1 ? i18n.t("notifications.newMessage") : i18n.t("notifications.newMessages", { count: delta }),
  }).catch(() => {});
}
