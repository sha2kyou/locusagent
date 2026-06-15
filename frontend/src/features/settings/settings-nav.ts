import { BarChart3, Cpu, ScrollText, Settings2, Terminal } from "lucide-react";

export const SETTINGS_NAV = [
  { to: "general", label: "通用", icon: Settings2, description: "主题、时区与菜单栏" },
  { to: "models", label: "模型与服务", icon: Cpu, description: "LLM、嵌入与第三方工具" },
  { to: "tools", label: "工具", icon: Terminal, description: "Terminal 开关与白名单" },
  { to: "usage", label: "用量统计", icon: BarChart3, description: "Token 与 API 调用" },
  { to: "logs", label: "日志", icon: ScrollText, description: "应用内操作记录" },
] as const;

export type SettingsNavId = (typeof SETTINGS_NAV)[number]["to"];
