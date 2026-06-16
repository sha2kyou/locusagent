import type { TFunction } from "i18next";
import i18n from "../../i18n/index.ts";
import type { NotificationEntry } from "@/api/types";

const BACKEND_SELF_IMPROVEMENT = "自我改进";
const BACKEND_SCHEDULED_TASK = "定时任务";
const BACKEND_ARTIFACT_SAVED_PREFIX = "产物已保存：";
const ARTIFACT_CATEGORY_RE = /^保存产物[（(](.+)[）)]$/;

function parseLegacyArtifactSavedTitle(title: string): { title: string; category?: string } | null {
  if (!title.startsWith(BACKEND_ARTIFACT_SAVED_PREFIX)) return null;
  const rest = title.slice(BACKEND_ARTIFACT_SAVED_PREFIX.length).trim();
  const match = rest.match(/^(.+)[（(](.+)[）)]$/);
  if (match) {
    return { title: match[1].trim(), category: match[2].trim() };
  }
  return { title: rest };
}

export function displayNotificationCategory(
  item: NotificationEntry,
  t: TFunction,
): string | null {
  const category = item.category?.trim() ?? "";
  if (category === BACKEND_SELF_IMPROVEMENT) {
    return t("notifications.category.selfImprovement");
  }
  if (category === BACKEND_SCHEDULED_TASK) {
    return t("notifications.category.scheduledTask");
  }
  if (ARTIFACT_CATEGORY_RE.test(category)) {
    return t("notifications.category.artifactSaved");
  }
  if (category) return category;
  if (item.title.startsWith(BACKEND_ARTIFACT_SAVED_PREFIX)) {
    return t("notifications.category.artifactSaved");
  }
  return null;
}

export function displayNotificationTitle(item: NotificationEntry, _t: TFunction): string {
  const category = item.category?.trim() ?? "";
  if (category === BACKEND_SELF_IMPROVEMENT) {
    return item.title;
  }
  const artifactCategory = category.match(ARTIFACT_CATEGORY_RE);
  if (artifactCategory) {
    return item.title;
  }
  const legacy = parseLegacyArtifactSavedTitle(item.title);
  if (legacy) {
    return legacy.title;
  }
  return item.title;
}

/** 通知铃铛面板仍用 title；toast 需说明发生了什么。 */
export function toastMessageForNotification(item: NotificationEntry): string {
  const category = item.category?.trim() ?? "";
  if (category === BACKEND_SELF_IMPROVEMENT) {
    const body = item.body?.trim();
    return body ? i18n.t("notifications.toast.selfImprovement", { body }) : item.title;
  }
  const artifact = category.match(ARTIFACT_CATEGORY_RE);
  if (artifact) {
    return i18n.t("notifications.toast.artifactSaved", {
      title: item.title,
      category: artifact[1],
    });
  }
  const legacy = parseLegacyArtifactSavedTitle(item.title);
  if (legacy) {
    if (legacy.category) {
      return i18n.t("notifications.toast.artifactSaved", {
        title: legacy.title,
        category: legacy.category,
      });
    }
    return item.title;
  }
  if (category === BACKEND_SCHEDULED_TASK) {
    return item.title;
  }
  return item.title;
}
