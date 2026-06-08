/** 流式重试与错误文案 */

export const AGENT_UNAVAILABLE = "AgentPod 暂时不可用，请稍后重试。";

export const AGENT_STARTING_RETRY_EXHAUSTED =
  "AgentPod 启动超时，请稍后再试；若持续失败请联系管理员。";

export const AGENT_COMPOSER_PLACEHOLDER = "给 AgentPod 发送消息…";

export const AUTH_LOAD_FAILED = "无法连接服务器，请稍后重试。";

export const STREAM_MAX_RETRIES = 5;

export function formatStreamRetryToast(attempt: number, retryAfterSec: number): string {
  return `AgentPod 启动中，${retryAfterSec}s 后重试（${attempt}/${STREAM_MAX_RETRIES}）`;
}

export function userMessageFromContainerError(
  code?: string,
  status?: number,
): string {
  if (code === "starting") return AGENT_STARTING_RETRY_EXHAUSTED;
  if (code === "unavailable") return AGENT_UNAVAILABLE;
  if (status === 503) return AGENT_STARTING_RETRY_EXHAUSTED;
  return "";
}
