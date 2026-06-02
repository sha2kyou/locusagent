import { apiGet, apiSend } from "./client";
import type {
  ActiveRunResponse,
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
  ScheduledTask,
  ScheduleKind,
  TimezoneConfig,
  UsageSummary,
  ToolToggleOverview,
  WorkspaceItem,
} from "./types";

// ---- 用户 / 认证 ----
export const getMe = (noAuthRedirect = false) =>
  apiGet<Me>("/api/me", { noAuthRedirect });

export const flashApiKey = () =>
  apiGet<{ api_key: string | null }>("/api/me/api-key/flash");

export const rotateApiKey = () =>
  apiSend<{ api_key: string }>("/api/me/api-key/rotate", "POST", {});

export const deleteAccount = (confirm_username: string) =>
  apiSend<{ ok: boolean }>("/api/me", "DELETE", { confirm_username });

export const ensureContainer = () =>
  apiSend<{ status: string; provision_status: string }>("/internal/containers/ensure", "POST", {});

// ---- 工作区 ----
export const listWorkspaces = () =>
  apiGet<{ default_workspace_id: string; items: WorkspaceItem[] }>("/api/workspaces");

export const createWorkspace = (body: { name: string; description?: string }) =>
  apiSend<{ item: WorkspaceItem }>("/api/workspaces", "POST", body);

export const updateWorkspace = (id: string, body: { name?: string; description?: string }) =>
  apiSend<{ item: WorkspaceItem }>(`/api/workspaces/${encodeURIComponent(id)}`, "PUT", body);

export const deleteWorkspace = (id: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspaces/${encodeURIComponent(id)}`, "DELETE");

// ---- 设置 ----
export const getUsageSummary = () => apiGet<UsageSummary>("/api/settings/usage-summary");

export const getTimezoneConfig = () => apiGet<TimezoneConfig>("/api/settings/timezone");

export const putTimezoneConfig = (body: { timezone: string }) =>
  apiSend<TimezoneConfig>("/api/settings/timezone", "PUT", body);

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

// ---- 会话 ----
export const listSessions = (limit = 50) =>
  apiGet<{ items: SessionMeta[] }>(`/api/workspace/sessions?limit=${limit}`);

export const getSessionMessages = (id: string) =>
  apiGet<{ items: Message[] }>(`/api/workspace/sessions/${encodeURIComponent(id)}`);

export const getActiveRun = (id: string) =>
  apiGet<ActiveRunResponse>(`/api/workspace/sessions/${encodeURIComponent(id)}/active-run`);

export const cancelRun = (id: string) =>
  apiSend<{ cancelled: boolean }>(`/api/workspace/sessions/${encodeURIComponent(id)}/cancel`, "POST", {});

export const deleteSession = (id: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/sessions/${encodeURIComponent(id)}`, "DELETE");

export const createAttachment = (body: {
  session_id?: string | null;
  name: string;
  size_bytes: number;
  kind: "text" | "image" | "other";
  mime_type?: string;
  text_content?: string;
  image_data_url?: string;
  processable: boolean;
  unsupported_reason?: string;
  truncated: boolean;
}) => apiSend<{
  id: string;
  name: string;
  kind: "text" | "image" | "other";
  mimeType?: string;
  text?: string;
  imageDataUrl?: string;
  processable: boolean;
  unsupportedReason?: string;
  truncated?: boolean;
}>("/api/workspace/attachments", "POST", body);

// ---- 技能 ----
export const listSkills = () => apiGet<{ items: Skill[] }>("/api/workspace/skills");

export const createSkill = (body: { name: string; description: string; body: string; triggers: string[] }) =>
  apiSend<Skill>("/api/workspace/skills", "POST", body);

export const updateSkill = (name: string, body: { description: string; body: string; triggers: string[] }) =>
  apiSend<Skill>(`/api/workspace/skills/${encodeURIComponent(name)}`, "PUT", body);

export const deleteSkill = (name: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/skills/${encodeURIComponent(name)}`, "DELETE");

// ---- MCP ----
export const listMcp = () => apiGet<{ items: McpServer[] }>("/api/workspace/mcp");

export const createMcp = (body: McpInput) => apiSend<McpServer>("/api/workspace/mcp", "POST", body);

export const testMcp = (body: McpInput) =>
  apiSend<{ connected: boolean; tool_count: number; runtime_error?: string }>("/api/workspace/mcp/test", "POST", body);

export const updateMcp = (name: string, body: McpInput) =>
  apiSend<McpServer>(`/api/workspace/mcp/${encodeURIComponent(name)}`, "PUT", body);

export const reconnectMcp = (name: string) =>
  apiSend<McpServer>(`/api/workspace/mcp/${encodeURIComponent(name)}`, "POST", {});

export const deleteMcp = (name: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/mcp/${encodeURIComponent(name)}`, "DELETE");

export const disconnectMcpOAuth = (name: string) =>
  apiSend<{ deleted: boolean }>(`/api/oauth/mcp/${encodeURIComponent(name)}`, "DELETE");

// ---- 工具开关 ----
export const listToolToggles = () => apiGet<ToolToggleOverview>("/api/workspace/tools");

export const updateBuiltinToolToggle = (name: string, enabled: boolean) =>
  apiSend<{ name: string; enabled: boolean }>(
    `/api/workspace/tools/builtin/${encodeURIComponent(name)}`,
    "PUT",
    { enabled },
  );

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
