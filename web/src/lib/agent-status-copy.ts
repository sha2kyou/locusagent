/** Agent 容器状态相关用户文案（ReadyGate、聊天底栏、流式重试、503 错误共用） */

export const AGENT_STARTING = "Agent 正在启动，请稍候…";

export const AGENT_STARTING_READY_GATE = AGENT_STARTING;

export const AGENT_PAUSED = "Agent 已休眠，发送消息将自动唤醒。";

export const AGENT_STOPPED = "Agent 已停止，发送消息将重新启动。";

export const AGENT_WAKING = "正在唤醒 Agent…";

export const PROVISION_FAILED_STATUS =
  "Agent 部署失败，请联系管理员检查服务端配置。";

export const PROVISION_FAILED_HINT = `${PROVISION_FAILED_STATUS}修复后可重试。`;

export const AGENT_UNAVAILABLE = "Agent 暂时不可用，请稍后重试。";

export const AGENT_STARTING_RETRY_EXHAUSTED =
  "Agent 启动超时，请稍后再试；若持续失败请联系管理员。";

export const AGENT_COMPOSER_PLACEHOLDER = "给 Agent 发送消息…";

export const AGENT_COMPOSER_NOT_READY = "Agent 未就绪，请稍候…";

export const AGENT_COMPOSER_FAILED = "Agent 部署失败，暂不可发送消息…";

/** 顶栏/设置等处的短标签 */
export const READINESS_LABEL_CREATING = "启动中";
export const READINESS_LABEL_FAILED = "部署失败";
export const READINESS_LABEL_PAUSED = "已休眠";
export const READINESS_LABEL_STOPPED = "已停止";
export const READINESS_LABEL_ABSENT = "未就绪";
export const READINESS_LABEL_READY = "已就绪";

export const AUTH_LOAD_FAILED = "无法连接服务器，请稍后重试。";

export const STREAM_MAX_RETRIES = 5;

/** 503 自动重试时的 toast */
export function formatStreamRetryToast(
  attempt: number,
  retryAfterSec: number,
  waking: boolean,
): string {
  if (waking && attempt === 1) {
    return `${AGENT_WAKING}${retryAfterSec}s 后重试。`;
  }
  return `Agent 启动中，${retryAfterSec}s 后重试（${attempt}/${STREAM_MAX_RETRIES}）`;
}

/** 代理/容器错误 → 用户可见文案 */
export function userMessageFromContainerError(
  code?: string,
  status?: number,
): string {
  if (code === "starting") return AGENT_STARTING_RETRY_EXHAUSTED;
  if (code === "unavailable") return AGENT_UNAVAILABLE;
  if (status === 503) return AGENT_STARTING_RETRY_EXHAUSTED;
  return "";
}
