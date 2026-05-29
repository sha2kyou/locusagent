// 后端 /api/* 契约类型（依据 host + agent 容器实现整理）

export interface Me {
  id: number;
  username: string;
  avatar_url: string | null;
  container_status: string; // absent | creating | running | paused | stopped ...
  provision_status: string; // pending | ready | failed
  llm_configured: boolean;
  llm_base_url: string | null;
  llm_model: string;
  agent_api_key_configured: boolean;
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
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  tool_calls?: (OpenAIToolCall | LegacyToolMeta)[] | null;
  tool_call_id?: string | null;
  run_id?: string | null;
  tokens?: number | null;
  created_at: string;
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
    delta: { role?: string; content?: string };
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
  connected: boolean;
  tools: McpTool[];
  tool_count: number;
  runtime_error?: string;
}

export interface McpInput {
  name: string;
  transport: "stdio" | "http";
  command?: string[];
  args?: string[];
  env?: Record<string, string>;
  url?: string;
}

export type MemoryAnchor = "identity" | "experience";

export interface MemoryEntry {
  id: number;
  content: string;
  anchor: MemoryAnchor;
  embedding_state: "pending" | "ready" | "failed";
  created_at: string;
}

export interface LLMConfig {
  base_url: string | null;
  model: string;
  configured: boolean;
  provision_action: "none" | "starting" | "applying";
}
