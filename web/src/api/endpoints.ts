import { apiGet, apiSend } from "./client";
import type {
  ActiveRunResponse,
  EnvVarEntry,
  ArtifactCategory,
  ArtifactEntry,
  LLMConfig,
  McpInput,
  McpServer,
  Me,
  MemoryAnchor,
  MemoryEntry,
  Message,
  SessionMeta,
  Skill,
  TavilyConfig,
  ToolToggleOverview,
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

// ---- 设置 / LLM ----
export const getLLMConfig = () => apiGet<LLMConfig>("/api/settings/llm");

export const putLLMConfig = (body: { base_url: string; model: string; api_key?: string }) =>
  apiSend<LLMConfig>("/api/settings/llm", "PUT", body);

export const getTavilyConfig = () => apiGet<TavilyConfig>("/api/settings/tavily");

export const putTavilyConfig = (body: { api_key: string }) =>
  apiSend<TavilyConfig>("/api/settings/tavily", "PUT", body);

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

export const createArtifactCategory = (name: string) =>
  apiSend<ArtifactCategory>("/api/workspace/artifact-categories", "POST", { name });

export const deleteArtifactCategory = (id: string) =>
  apiSend<{ deleted: boolean }>(
    `/api/workspace/artifact-categories/${encodeURIComponent(id)}`,
    "DELETE",
  );

// ---- 产物 ----
export const listArtifacts = (categoryId?: string) =>
  apiGet<{ items: ArtifactEntry[] }>(
    categoryId
      ? `/api/workspace/artifacts?category_id=${encodeURIComponent(categoryId)}`
      : "/api/workspace/artifacts",
  );

export const getArtifact = (id: string) =>
  apiGet<ArtifactEntry>(`/api/workspace/artifacts/${encodeURIComponent(id)}`);

export const updateArtifact = (
  id: string,
  body: { title?: string; content?: string; category_id?: string },
) => apiSend<{ updated: boolean }>(`/api/workspace/artifacts/${encodeURIComponent(id)}`, "PUT", body);

export const deleteArtifact = (id: string) =>
  apiSend<{ deleted: boolean }>(`/api/workspace/artifacts/${encodeURIComponent(id)}`, "DELETE");
