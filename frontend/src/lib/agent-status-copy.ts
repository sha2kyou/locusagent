import i18n from "../i18n/index.ts";

/** 流式重试与错误文案 */

export const STREAM_MAX_RETRIES = 5;

export function getAgentUnavailable(): string {
  return i18n.t("copy.agent.unavailable");
}

export function getAgentStartingRetryExhausted(): string {
  return i18n.t("copy.agent.startingTimeout");
}

export function getAgentComposerPlaceholder(): string {
  return i18n.t("copy.agent.composerPlaceholder");
}

export function getAuthLoadFailed(): string {
  return i18n.t("copy.agent.authLoadFailed");
}

export function formatStreamRetryToast(attempt: number, retryAfterSec: number): string {
  return i18n.t("copy.agent.streamRetry", {
    seconds: retryAfterSec,
    attempt,
    max: STREAM_MAX_RETRIES,
  });
}

export function userMessageFromContainerError(
  code?: string,
  status?: number,
): string {
  if (code === "starting") return getAgentStartingRetryExhausted();
  if (code === "unavailable") return getAgentUnavailable();
  if (status === 503) return getAgentStartingRetryExhausted();
  return "";
}
