import type { NotificationEntry } from "@/api/types";

const ARTIFACT_CATEGORY_RE = /^保存产物[（(](.+)[）)]$/;

/** 通知铃铛面板仍用 title；toast 需说明发生了什么。 */
export function toastMessageForNotification(item: NotificationEntry): string {
  const category = item.category?.trim() ?? "";
  const artifact = category.match(ARTIFACT_CATEGORY_RE);
  if (artifact) {
    return `产物已保存：${item.title}（${artifact[1]}）`;
  }
  if (item.title.startsWith("产物已保存：")) return item.title;
  return item.title;
}
