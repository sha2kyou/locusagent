import { ApiError, apiGet, apiSend, getWorkspaceId, type RequestOptions } from "./client";
import i18n from "@/i18n";
import { filePreviewKind, isFilePreviewable } from "@/lib/file-preview";
import type {
  ActiveRunResponse,
  AppConfig,
  AppConfigUpdate,
  EnvVarEntry,
  ArtifactCategory,
  ArtifactEntry,
  McpInput,
  McpServer,
  Me,
  MemoryAnchor,
  MemoryEntry,
  Message,
  NotificationEntry,
  SessionMeta,
  Skill,
  SkillFileContent,
  SkillFileEntry,
  SkillInstallResult,
  ScheduledTask,
  ScheduleKind,
  TimezoneConfig,
  ToolTimingItem,
  LocaleConfig,
  BackendLogs,
  EmbeddingProgress,
  UsageSummary,
  WorkspaceItem,
} from "./types";

// ---- 用户 / 认证 ----
export const getMe = (noAuthRedirect = false) =>
  apiGet<Me>("/api/me", { noAuthRedirect });

// ---- 工作区 ----
export const listWorkspaces = () =>
  apiGet<{ default_workspace_id: string; items: WorkspaceItem[] }>("/api/workspaces");

export const createWorkspace = (body: { name: string; description?: string }) =>
  apiSend<{ item: WorkspaceItem }>("/api/workspaces", "POST", body);

export const updateWorkspace = (id: string, body: { name?: string; description?: string }) =>
  apiSend<{ item: WorkspaceItem }>(`/api/workspaces/${encodeURIComponent(id)}`, "PUT", body);

export const deleteWorkspace = (id: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspaces/${encodeURIComponent(id)}`, "DELETE");

export const copyWorkspace = (id: string, body?: { name?: string }) =>
  apiSend<{ item: WorkspaceItem }>(
    `/api/workspaces/${encodeURIComponent(id)}/copy`,
    "POST",
    body ?? {},
  );

// ---- 设置 ----
export const getUsageSummary = () => apiGet<UsageSummary>("/api/settings/usage-summary");

export const getTimezoneConfig = () => apiGet<TimezoneConfig>("/api/settings/timezone");

export const putTimezoneConfig = (body: { timezone: string }) =>
  apiSend<TimezoneConfig>("/api/settings/timezone", "PUT", body);

export const getLocaleConfig = () => apiGet<LocaleConfig>("/api/settings/locale");

export const putLocaleConfig = (body: { locale: string }) =>
  apiSend<LocaleConfig>("/api/settings/locale", "PUT", body);

export const getAppConfig = () => apiGet<AppConfig>("/api/settings/app-config");

export const putAppConfig = (body: AppConfigUpdate) =>
  apiSend<AppConfig>("/api/settings/app-config", "PUT", body);

export const getBackendLogs = (opts?: { lines?: number }, signal?: AbortSignal) => {
  const params = new URLSearchParams();
  if (opts?.lines != null) params.set("lines", String(opts.lines));
  const q = params.toString();
  return apiGet<BackendLogs>(`/api/settings/backend-logs${q ? `?${q}` : ""}`, { signal });
};

export const exportSettings = () => apiGet<Record<string, unknown>>("/api/settings/export");

export const importSettings = (body: Record<string, unknown>) =>
  apiSend<AppConfig>("/api/settings/import", "POST", body);

// ---- 定时任务 ----
export const listScheduledTasks = () => apiGet<{ items: ScheduledTask[] }>("/api/scheduled-tasks");

export const createScheduledTask = (body: {
  title: string;
  prompt: string;
  schedule_kind: ScheduleKind;
  enabled?: boolean;
  notify?: boolean;
  cron_expr?: string;
  run_at?: string;
}) => apiSend<{ item: ScheduledTask }>("/api/scheduled-tasks", "POST", body);

export const updateScheduledTask = (
  id: number,
  body: {
    title?: string;
    prompt?: string;
    enabled?: boolean;
    notify?: boolean;
    cron_expr?: string;
    run_at?: string;
  },
) => apiSend<{ item: ScheduledTask }>(`/api/scheduled-tasks/${id}`, "PUT", body);

export const deleteScheduledTask = (id: number) =>
  apiSend<{ deleted: boolean }>(`/api/scheduled-tasks/${id}`, "DELETE");

export const runScheduledTaskNow = (id: number) =>
  apiSend<{ item: ScheduledTask }>(`/api/scheduled-tasks/${id}/run`, "POST");

// ---- 会话 ----
export const listSessions = (limit = 20) =>
  apiGet<{ items: SessionMeta[] }>(`/api/workspace/sessions?limit=${limit}`);

export const getSessionMessages = (id: string) =>
  apiGet<{ items: Message[]; todo_plan?: unknown }>(`/api/workspace/sessions/${encodeURIComponent(id)}`);

export const getActiveRun = (id: string) =>
  apiGet<ActiveRunResponse>(`/api/workspace/sessions/${encodeURIComponent(id)}/active-run`);

export const cancelRun = (id: string) =>
  apiSend<{ cancelled: boolean }>(`/api/workspace/sessions/${encodeURIComponent(id)}/cancel`, "POST", {});

export const listToolTimings = (sessionId: string) =>
  apiGet<{ items: ToolTimingItem[] }>(
    `/api/workspace/sessions/${encodeURIComponent(sessionId)}/tool-timings`,
  );

export const listTerminalApprovals = (sessionId: string) =>
  apiGet<{
    items: Array<{
      approval_id: string;
      command: string;
      head: string;
      tool_call_id: string;
      run_id: string;
      timeout_seconds: number;
      expires_at: number;
    }>;
  }>(`/api/workspace/sessions/${encodeURIComponent(sessionId)}/terminal-approvals`);

export const resolveTerminalApproval = (
  sessionId: string,
  approvalId: string,
  choice: "once" | "always" | "deny" | "always_deny",
) =>
  apiSend<{ ok: boolean; choice?: string; error?: string }>(
    `/api/workspace/sessions/${encodeURIComponent(sessionId)}/terminal-approvals/${encodeURIComponent(approvalId)}`,
    "POST",
    { choice },
  );

export const deleteSession = (id: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/sessions/${encodeURIComponent(id)}`, "DELETE");

export const createAttachment = (
  body: {
    session_id?: string | null;
    name: string;
    size_bytes: number;
    kind: "text" | "image" | "other";
    mime_type?: string;
    text_content?: string;
    image_data_url?: string;
    file_data_base64?: string;
    content_sha256?: string;
    file_sha256?: string;
    processable: boolean;
    unsupported_reason?: string;
    truncated: boolean;
  },
  opts?: RequestOptions,
) =>
  apiSend<{
  id: string;
  name: string;
  kind: "text" | "image" | "other";
  mimeType?: string;
  text?: string;
  imageDataUrl?: string;
  processable: boolean;
  unsupportedReason?: string;
  truncated?: boolean;
  reused?: boolean;
}>("/api/workspace/attachments", "POST", body, opts);

export function attachmentDownloadUrl(id: string): string {
  const workspaceId = getWorkspaceId();
  const base = `/api/workspace/attachments/${encodeURIComponent(id)}/download`;
  if (!workspaceId) return base;
  return `${base}?workspace_id=${encodeURIComponent(workspaceId)}`;
}

export interface AttachmentPreviewPayload {
  content?: string;
  imageSrc?: string;
  documentSrc?: string;
  mimeType?: string;
}

/** 从服务端附件拉取可预览内容（与上传/交付来源无关）。 */
export async function fetchAttachmentPreview(
  id: string,
  filename: string,
  mimeType?: string,
): Promise<AttachmentPreviewPayload | null> {
  if (!isFilePreviewable(filename, mimeType)) return null;

  const res = await fetch(attachmentDownloadUrl(id), { credentials: "same-origin" });
  if (res.status === 401) {
    throw new ApiError(i18n.t("errors.unauthenticated"), { status: 401, code: "unauthenticated" });
  }
  if (!res.ok) {
    throw new ApiError(i18n.t("errors.downloadFailed", { status: res.status }), { status: res.status });
  }

  const blob = await res.blob();
  const resolvedMime = mimeType || blob.type || "application/octet-stream";
  const kind = filePreviewKind(filename, resolvedMime);
  if (kind === "image") {
    return { imageSrc: URL.createObjectURL(blob), mimeType: resolvedMime };
  }
  if (kind === "pdf") {
    const pdfMime = "application/pdf";
    const pdfBlob = blob.type === pdfMime ? blob : new Blob([blob], { type: pdfMime });
    return { documentSrc: URL.createObjectURL(pdfBlob), mimeType: pdfMime };
  }
  return { content: await blob.text(), mimeType: resolvedMime };
}

/** 保留：需编程触发下载时使用（优先用 attachmentDownloadUrl + <a download>） */
export async function downloadAttachment(id: string, filename: string): Promise<void> {
  const res = await fetch(attachmentDownloadUrl(id), { credentials: "same-origin" });
  if (res.status === 401) {
    throw new ApiError(i18n.t("errors.unauthenticated"), { status: 401, code: "unauthenticated" });
  }
  if (!res.ok) {
    const ct = res.headers.get("content-type") || "";
    const data: unknown = ct.includes("json") ? await res.json().catch(() => null) : await res.text();
    throw new ApiError(i18n.t("errors.downloadFailed", { status: res.status }), { status: res.status, data });
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "download";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

// ---- 技能 ----
export const listSkills = () => apiGet<{ items: Skill[] }>("/api/workspace/skills");

export const createSkill = (body: { name: string; description: string; body: string }) =>
  apiSend<Skill>("/api/workspace/skills", "POST", body);

export const updateSkill = (name: string, body: { description: string; body: string }) =>
  apiSend<Skill>(`/api/workspace/skills/${encodeURIComponent(name)}`, "PUT", body);

export const deleteSkill = (name: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/skills/${encodeURIComponent(name)}`, "DELETE");

export const listSkillFiles = (name: string) =>
  apiGet<{ items: SkillFileEntry[] }>(`/api/workspace/skills/${encodeURIComponent(name)}/files`);

export const getSkillFile = (name: string, path: string) =>
  apiGet<SkillFileContent>(
    `/api/workspace/skills/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`,
  );

export const installSkill = (body: { url: string; path?: string; overwrite?: boolean }) =>
  apiSend<SkillInstallResult>("/api/workspace/skills/install", "POST", body);

// ---- MCP ----
export const listMcp = (opts?: { sync?: boolean }) =>
  apiGet<{ items: McpServer[] }>(`/api/workspace/mcp${opts?.sync ? "?sync=1" : ""}`);

export const createMcp = (body: McpInput) => apiSend<McpServer>("/api/workspace/mcp", "POST", body);

export const updateMcp = (name: string, body: McpInput) =>
  apiSend<McpServer>(`/api/workspace/mcp/${encodeURIComponent(name)}`, "PUT", body);

export const reconnectMcp = (name: string) =>
  apiSend<McpServer>(`/api/workspace/mcp/${encodeURIComponent(name)}`, "POST", {});

export const deleteMcp = (name: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/mcp/${encodeURIComponent(name)}`, "DELETE");

export const disconnectMcpOAuth = (name: string) =>
  apiSend<{ deleted: boolean }>(`/api/oauth/mcp/${encodeURIComponent(name)}`, "DELETE");

export const getMcpOAuthAuthorizeUrl = (server: string, workspaceId: string) => {
  const params = new URLSearchParams({ server, workspace_id: workspaceId });
  return apiGet<{ authorize_url: string }>(`/api/oauth/mcp/authorize-url?${params.toString()}`);
};

// ---- 记忆 ----
export const listMemory = (limit = 100) =>
  apiGet<{ items: MemoryEntry[] }>(`/api/workspace/memory?limit=${limit}`);

export const createMemory = (body: { content: string; anchor: MemoryAnchor }) =>
  apiSend<{ id: number }>("/api/workspace/memory", "POST", body);

export const updateMemory = (id: number, body: { content?: string; anchor?: MemoryAnchor }) =>
  apiSend<{ updated: boolean }>(`/api/workspace/memory/${id}`, "PUT", body);

export const deleteMemory = (id: number) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/memory/${id}`, "DELETE");

// ---- 环境变量 ----
export const listEnvVars = (limit = 200) =>
  apiGet<{ items: EnvVarEntry[] }>(`/api/workspace/env-vars?limit=${limit}`);

export const createEnvVar = (body: { name: string; value: string; description?: string }) =>
  apiSend<{ id: number }>("/api/workspace/env-vars", "POST", body);

export const updateEnvVar = (id: number, body: { name?: string; value?: string; description?: string }) =>
  apiSend<{ updated: boolean }>(`/api/workspace/env-vars/${id}`, "PUT", body);

export const deleteEnvVar = (id: number) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/env-vars/${id}`, "DELETE");

export const getEmbeddingProgress = (signal?: AbortSignal) =>
  apiGet<EmbeddingProgress>("/api/workspace/embedding-progress", { signal });

export const recallEnvVars = (body: { query: string; top_k?: number }) =>
  apiSend<{ items: EnvVarEntry[] }>("/api/workspace/env-vars/recall", "POST", body);

// ---- 产物类目（子菜单） ----
export const listArtifactCategories = () =>
  apiGet<{ items: ArtifactCategory[] }>("/api/workspace/artifact-categories");

export const createArtifactCategory = (name: string, description = "") =>
  apiSend<ArtifactCategory>("/api/workspace/artifact-categories", "POST", { name, description });

export const updateArtifactCategory = (id: string, body: { name?: string; description?: string }) =>
  apiSend<{ updated: boolean }>(`/api/workspace/artifact-categories/${encodeURIComponent(id)}`, "PUT", body);

export const deleteArtifactCategory = (id: string) =>
  apiSend<{ deleted: boolean }>(
    `/api/workspace/artifact-categories/${encodeURIComponent(id)}`,
    "DELETE",
  );

// ---- 产物 ----
export const listArtifacts = (categoryId: string) =>
  apiGet<{ items: ArtifactEntry[] }>(
    `/api/workspace/artifacts?category_id=${encodeURIComponent(categoryId)}`,
  );

export const getArtifact = (id: string) =>
  apiGet<ArtifactEntry>(`/api/workspace/artifacts/${encodeURIComponent(id)}`);

export const updateArtifact = (
  id: string,
  body: { title?: string; content?: string; category_id?: string },
) => apiSend<{ updated: boolean }>(`/api/workspace/artifacts/${encodeURIComponent(id)}`, "PUT", body);

export const deleteArtifact = (id: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/artifacts/${encodeURIComponent(id)}`, "DELETE");

// ---- 站内通知 ----
export const listNotifications = (limit = 50) =>
  apiGet<{ items: NotificationEntry[]; unread_count: number }>(
    `/api/notifications?limit=${limit}`,
  );

export const getUnreadNotificationCount = () =>
  apiGet<{ count: number }>("/api/notifications/unread-count");

export const markNotificationRead = (id: number) =>
  apiSend<{ ok: boolean }>(`/api/notifications/${id}/read`, "POST", {});

export const markAllNotificationsRead = () =>
  apiSend<{ updated: number }>("/api/notifications/read-all", "POST", {});

export const deleteNotification = (id: number) =>
  apiSend<{ deleted: boolean }>(`/api/notifications/${id}`, "DELETE");
