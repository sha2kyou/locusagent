import i18n from "../i18n/index.ts";

const DEFAULT_MAX = 48;

export function truncateToastLabel(text: string, max = DEFAULT_MAX): string {
  const flat = text.trim().replace(/\s+/g, " ");
  if (!flat) return i18n.t("copy.toast.unnamed");
  if (flat.length <= max) return flat;
  return `${flat.slice(0, max - 1)}…`;
}

export type ToastActionKey =
  | "deleted"
  | "added"
  | "updated"
  | "reconnected"
  | "oauthDisconnected"
  | "started";

export type ToastKindKey =
  | "session"
  | "skill"
  | "memory"
  | "workspace"
  | "category"
  | "artifact"
  | "scheduledTask"
  | "envVar"
  | "mcpService";

export function toastAction(action: ToastActionKey, name: string, kind?: ToastKindKey): string {
  const label = truncateToastLabel(name);
  const actionText = i18n.t(`toast.actions.${action}`);
  if (kind) {
    const kindText = i18n.t(`toast.kinds.${kind}`);
    return i18n.t("toast.actions.withKind", { action: actionText, kind: kindText, name: label });
  }
  return i18n.t("toast.actions.withoutKind", { action: actionText, name: label });
}
