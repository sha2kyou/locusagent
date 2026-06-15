import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { PageContainer } from "@/components/PageContainer";
import { SecondarySidebar } from "@/components/SecondarySidebar";
import { stripWorkspacePrefix, withWorkspacePrefix } from "@/app/workspace-route";
import {
  secondarySidebarHeaderClass,
  secondarySidebarListClass,
  secondarySidebarRowClass,
  secondarySidebarRowLabelClass,
  secondarySidebarScrollClass,
  secondarySidebarTitleClass,
} from "@/components/secondary-sidebar-styles";
import { SETTINGS_NAV } from "./settings-nav";

const PAGE_META: Record<string, { title: string; subtitle: string }> = {
  general: { title: "通用", subtitle: "主题与时区" },
  models: { title: "模型与服务", subtitle: "LLM、向量嵌入与第三方工具" },
  tools: { title: "工具", subtitle: "Terminal 开关、白名单与禁止项" },
  usage: { title: "用量统计", subtitle: "按场景汇总 Token 与 API 调用" },
  logs: { title: "日志", subtitle: "MCP、技能、对话等主要操作记录" },
};

export function SettingsRoute() {
  const location = useLocation();
  const { workspaceId } = stripWorkspacePrefix(location.pathname);
  const base = withWorkspacePrefix("/settings", workspaceId);
  const segment = location.pathname.split("/").filter(Boolean).pop() ?? "general";
  const meta = PAGE_META[segment] ?? PAGE_META.general;

  return (
    <div className="flex h-full min-h-0">
      <SecondarySidebar mobileOpen={false}>
        <div className={secondarySidebarHeaderClass}>
          <span className={secondarySidebarTitleClass}>设置</span>
        </div>
        <div className={secondarySidebarScrollClass}>
          <nav className={secondarySidebarListClass}>
            {SETTINGS_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={`${base}/${item.to}`}
                title={item.description}
                className={({ isActive }) => secondarySidebarRowClass(isActive)}
              >
                <item.icon className="size-4 shrink-0 opacity-70" strokeWidth={1.75} />
                <span className={secondarySidebarRowLabelClass}>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </SecondarySidebar>

      <div className="min-w-0 flex-1 overflow-y-auto">
        <PageContainer title={meta.title} subtitle={meta.subtitle} embedded>
          <Outlet />
        </PageContainer>
      </div>
    </div>
  );
}

export function SettingsIndexRedirect() {
  const location = useLocation();
  const { workspaceId } = stripWorkspacePrefix(location.pathname);
  return <Navigate to={withWorkspacePrefix("/settings/general", workspaceId)} replace />;
}
