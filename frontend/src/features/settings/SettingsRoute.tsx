import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
import { SETTINGS_NAV, SETTINGS_PAGE_META, type SettingsNavId } from "./settings-nav";

export function SettingsRoute() {
  const { t } = useTranslation();
  const location = useLocation();
  const { workspaceId } = stripWorkspacePrefix(location.pathname);
  const base = withWorkspacePrefix("/settings", workspaceId);
  const segment = (location.pathname.split("/").filter(Boolean).pop() ?? "general") as SettingsNavId;
  const meta = SETTINGS_PAGE_META[segment] ?? SETTINGS_PAGE_META.general;

  return (
    <div className="flex h-full min-h-0">
      <SecondarySidebar mobileOpen={false}>
        <div className={secondarySidebarHeaderClass}>
          <span className={secondarySidebarTitleClass}>{t("settings.title")}</span>
        </div>
        <div className={secondarySidebarScrollClass}>
          <nav className={secondarySidebarListClass}>
            {SETTINGS_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={`${base}/${item.to}`}
                title={t(item.descriptionKey)}
                className={({ isActive }) => secondarySidebarRowClass(isActive)}
              >
                <item.icon className="size-4 shrink-0 opacity-70" strokeWidth={1.75} />
                <span className={secondarySidebarRowLabelClass}>{t(item.labelKey)}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </SecondarySidebar>

      <div className="min-w-0 flex-1 overflow-y-auto">
        <PageContainer title={t(meta.titleKey)} subtitle={t(meta.subtitleKey)} embedded>
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
