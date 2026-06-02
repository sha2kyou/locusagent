// 后端 /api/* 契约类型（依据 host + agent 容器实现整理）

export interface Me {
  id: number;
  username: string;
  avatar_url: string | null;
  current_workspace_id?: string;
  container_status: string; // absent | creating | running | paused | stopped ...
  provision_status: string; // pending | ready | failed
  agent_api_key_configured: boolean;
  attachment_max_bytes: number;
}

export interface WorkspaceItem {
  id: string;
  name: string;
  description: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SessionMeta {
  id: string;
  title: string;
  status: string;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface OpenAIToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface LegacyToolMeta {
  event_type: "tool_call" | "tool_result";
  tool_call_id?: string;
  tool_name?: string;
  tool_kind?: ToolKind;
  preview?: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant" | "tool" | "system" | "context_summary";
  content: string;
  reasoning_content?: string;
  attachments?: {
    id: string;
    name: string;
    kind: "text" | "image" | "other";
    mimeType?: string;
    text?: string;
    imageDataUrl?: string;
    processable: boolean;
    unsupportedReason?: string;
    truncated?: boolean;
  }[];
  tool_calls?: (OpenAIToolCall | LegacyToolMeta | Record<string, unknown>)[] | null;
  tool_call_id?: string | null;
  run_id?: string | null;
  tokens?: number | null;
  created_at: string;
  context_state?: "active" | "archived";
  archive_batch_id?: string | null;
  archived_at?: string | null;
}

export interface ActiveRun {
  id: string;
  session_id: string;
  status: "running" | "completed" | "failed";
  assistant_message_id: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  assistant_message?: Message | null;
}

export interface ActiveRunResponse {
  run: ActiveRun | null;
}

export type ToolKind = "skill" | "mcp" | "memory" | "tool";

// chat/completions 流式 chunk（OpenAI 兼容 + x_ 扩展，扩展字段与 choices 同级）
export interface ChatChunk {
  id?: string;
  object?: string;
  created?: number;
  model?: string;
  choices?: {
    index: number;
    delta: { role?: string; content?: string; reasoning_content?: string };
    finish_reason: string | null;
  }[];
  session_id?: string;
  run_id?: string;
  x_event?: "tool_call" | "tool_result" | "error";
  x_tool_name?: string;
  x_tool_kind?: ToolKind;
  x_tool_id?: string;
  x_tool_call_id?: string;
  x_preview?: string;
  x_message?: string;
}

export interface Skill {
  name: string;
  description: string;
  triggers: string[];
  source: "private" | "public";
  body: string;
  enabled?: boolean;
}

export interface McpTool {
  name: string;
  full_name: string;
  description: string;
  input_schema: unknown;
  schema_summary: string;
}

export interface McpServer {
  name: string;
  transport: "stdio" | "http";
  command?: string[];
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  auth?: "none" | "oauth";
  connected: boolean;
  tools: McpTool[];
  tool_count: number;
  runtime_error?: string;
  enabled?: boolean;
  oauth_required?: boolean;
  oauth_connected?: boolean | null;
}

export interface McpInput {
  name: string;
  transport: "stdio" | "http";
  command?: string[];
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  auth?: "none" | "oauth";
}

export interface ToolToggleItem {
  name: string;
  description?: string;
  source?: "private" | "public";
  transport?: "stdio" | "http";
  enabled: boolean;
}

export interface ToolToggleOverview {
  builtin_tools: ToolToggleItem[];
}

export type MemoryAnchor = "identity" | "experience";

export interface MemoryEntry {
  id: number;
  content: string;
  anchor: MemoryAnchor;
  embedding_state: "pending" | "ready" | "failed";
  created_at: string;
}

export interface EnvVarEntry {
  id: number;
  name: string;
  value: string;
  description: string;
  embedding_state: "pending" | "ready" | "failed";
  created_at: string;
  updated_at: string;
}

export interface TimezoneConfig {
  timezone: string;
}

export interface UsageSummaryRow {
  scenario: string;
  label: string;
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  api_calls: number;
  event_count: number;
}

export interface UsageSummary {
  items: UsageSummaryRow[];
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    api_calls: number;
    event_count: number;
  };
}

export type ScheduleKind = "once" | "cron";

export interface ScheduledTask {
  id: number;
  title: string;
  prompt: string;
  schedule_kind: ScheduleKind;
  cron_expr: string | null;
  run_at: string | null;
  enabled: boolean;
  notify: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  last_session_id: string | null;
  last_error: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type NotificationKind = "info" | "success" | "warning" | "error";

export interface NotificationEntry {
  id: number;
  kind: NotificationKind;
  category: string | null;
  title: string;
  body: string;
  link: string | null;
  read: boolean;
  created_at: string;
  read_at: string | null;
}

export interface ArtifactCategory {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export type ArtifactType = "markdown" | "latex" | "html" | "text";

export interface ArtifactEntry {
  id: string;
  category_id: string;
  type: ArtifactType;
  title: string;
  content: string;
  created_at: string;
  updated_at: string;
}
