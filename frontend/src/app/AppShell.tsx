import { createContext, Suspense, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Brain,
  ChevronsLeft,
  Clock,
  FolderOpen,
  Menu,
  MessagesSquare,
  PanelLeft,
  Plug,
  KeyRound,
  Settings,
  Sparkles,
} from "lucide-react";
import { DesktopWindowDragOverlay } from "@/app/DesktopTitlebarSpacer";
import { desktopDragRegionProps } from "@/lib/desktop-app";
import { subscribeWorkspacesChanged } from "@/lib/workspace-events";
import { cn } from "@/lib/utils";
import { ArtifactsNav } from "@/features/artifacts/ArtifactsNav";
import { useAuth } from "./auth";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { listWorkspaces } from "@/api/endpoints";
import type { WorkspaceItem } from "@/api/types";
import { isChatRoutePath, stripWorkspacePrefix, withWorkspacePrefix } from "./workspace-route";
import {
  sidebarNavGroupDividerClass,
  sidebarNavGroupDividerLineClass,
  sidebarNavContainerClass,
  sidebarNavIconClass,
  sidebarNavIconSlotClass,
  sidebarNavLabelClass,
  sidebarNavRowClass,
  sidebarPrimaryOffsetClass,
  sidebarPrimaryWidthClass,
} from "./sidebar-nav-styles";

interface ShellApi {
  /** 路由可注入移动端顶栏右侧操作（如会话抽屉开关） */
  setMobileAction: (node: ReactNode) => void;
}
const ShellContext = createContext<ShellApi | null>(null);
export function useShell() {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used within AppShell");
  return ctx;
}

type NavEntry = { to: string; labelKey: string; icon: typeof MessagesSquare };

const NAV_PRIMARY: NavEntry[] = [{ to: "/chat", labelKey: "nav.chat", icon: MessagesSquare }];
const NAV_CAPABILITIES: NavEntry[] = [
  { to: "/skills", labelKey: "nav.skills", icon: Sparkles },
  { to: "/mcp", labelKey: "nav.mcp", icon: Plug },
];
const NAV_CONTEXT: NavEntry[] = [
  { to: "/memory", labelKey: "nav.memory", icon: Brain },
  { to: "/env-vars", labelKey: "nav.envVars", icon: KeyRound },
];
const NAV_WORKSPACE: NavEntry = { to: "/workspaces", labelKey: "nav.workspaces", icon: FolderOpen };
const NAV_AUTOMATION: NavEntry[] = [{ to: "/scheduled-tasks", labelKey: "nav.scheduledTasks", icon: Clock }];

const EXPAND_KEY = "apod-nav-expanded";

export function AppShell() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [expanded, setExpanded] = useState(
    () => localStorage.getItem(EXPAND_KEY) !== "0",
  );
  const [navOpen, setNavOpen] = useState(false);
  const [mobileAction, setMobileAction] = useState<ReactNode>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const navListRef = useRef<HTMLElement>(null);
  const defaultWorkspaceId = workspaces.find((w) => w.is_default)?.id ?? "";
  const currentWorkspace = workspaces.find((w) => w.id === me?.current_workspace_id) ?? null;
  const currentWorkspaceLabel = currentWorkspace?.name || t("nav.defaultWorkspace");
  const isDefaultWorkspace = !!currentWorkspace && currentWorkspace.is_default;
  const routeWorkspace = stripWorkspacePrefix(location.pathname);
  const onChatRoute = isChatRoutePath(location.pathname);
  const workspacePrefix = me?.current_workspace_id && !isDefaultWorkspace ? `/w/${me.current_workspace_id}` : "";

  useEffect(() => {
    localStorage.setItem(EXPAND_KEY, expanded ? "1" : "0");
  }, [expanded]);

  const refreshWorkspaces = useCallback(() => {
    if (!me) return;
    void listWorkspaces()
      .then((res) => setWorkspaces(res.items))
      .catch(() => setWorkspaces([]));
  }, [me]);

  useEffect(() => {
    refreshWorkspaces();
  }, [refreshWorkspaces, me?.current_workspace_id]);

  useEffect(() => subscribeWorkspacesChanged(refreshWorkspaces), [refreshWorkspaces]);

  useEffect(() => {
    if (onChatRoute) return;
    if (!me?.current_workspace_id || !defaultWorkspaceId) return;
    const shouldUsePrefix = me.current_workspace_id !== defaultWorkspaceId;
    const targetPath = routeWorkspace.path === "/" ? "/chat" : routeWorkspace.path;
    if (shouldUsePrefix && !routeWorkspace.workspaceId) {
      navigate(withWorkspacePrefix(targetPath, me.current_workspace_id), { replace: true });
      return;
    }
    if (!shouldUsePrefix && routeWorkspace.workspaceId) {
      navigate(targetPath, { replace: true });
    }
  }, [
    defaultWorkspaceId,
    me?.current_workspace_id,
    navigate,
    onChatRoute,
    routeWorkspace.path,
    routeWorkspace.workspaceId,
  ]);

  return (
    <ShellContext.Provider value={{ setMobileAction }}>
      <DesktopWindowDragOverlay
        mainOffsetClassName={
          expanded
            ? cn("left-0", sidebarPrimaryOffsetClass.expanded)
            : cn("left-0", sidebarPrimaryOffsetClass.collapsed)
        }
      />
      <div className="flex h-full">
        {navOpen && (
          <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setNavOpen(false)} />
        )}

        <aside
          className={cn(
            "apod-glass-sidebar fixed inset-y-0 left-0 z-50 flex flex-col transition-transform duration-200",
            sidebarPrimaryWidthClass.mobile,
            navOpen ? "translate-x-0" : "-translate-x-full",
            "md:static md:z-auto md:translate-x-0 md:border-r md:border-sidebar-border md:transition-[width]",
            expanded ? sidebarPrimaryWidthClass.expanded : sidebarPrimaryWidthClass.collapsed,
          )}
        >
          <div
            {...desktopDragRegionProps("deep")}
            className="apod-sidebar-header hidden shrink-0 md:block"
          />

          <div className="h-12 shrink-0 md:hidden" />

          <nav ref={navListRef} className={sidebarNavContainerClass(expanded)}>
            {NAV_PRIMARY.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}
            <ArtifactsNav basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            <NavRow {...NAV_WORKSPACE} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />

            <NavGroupDivider expanded={expanded} />
            {NAV_CAPABILITIES.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}

            <NavGroupDivider expanded={expanded} />
            {NAV_CONTEXT.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}

            <NavGroupDivider expanded={expanded} />
            {NAV_AUTOMATION.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}
          </nav>

          <div
            className={cn(
              "relative shrink-0 border-t border-sidebar-border/40 p-2.5",
              !expanded && "md:flex md:flex-col md:items-center md:p-2",
            )}
          >
            {!isDefaultWorkspace && (
              <div
                className={cn(
                  "mb-2 inline-flex w-fit max-w-full items-center gap-1.5 rounded-md border border-border/50 bg-surface/40 px-2 py-1 text-[11px] text-muted-foreground/70",
                  !expanded && "md:mb-2 md:justify-center md:px-1.5",
                )}
                title={currentWorkspace?.description || currentWorkspaceLabel}
              >
                <span className={cn("max-w-full truncate leading-normal", !expanded && "md:hidden")}>
                  {currentWorkspaceLabel}
                </span>
                {!expanded && <span className="hidden md:block text-[10px]">WS</span>}
              </div>
            )}
            <NavLink
              to={`${workspacePrefix}/settings`}
              title={t("nav.settings")}
              onClick={() => setNavOpen(false)}
              className={({ isActive }) =>
                cn(
                  sidebarNavRowClass(isActive, expanded),
                  "w-full",
                )
              }
            >
              <span className={sidebarNavIconSlotClass} aria-hidden>
                <Settings className={sidebarNavIconClass} strokeWidth={1.75} />
              </span>
              <span className={sidebarNavLabelClass(expanded)}>{t("nav.settings")}</span>
            </NavLink>
          </div>

          <div className={cn("hidden shrink-0 border-t border-sidebar-border/40 p-2 md:block", !expanded && "md:flex md:justify-center")}>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              title={expanded ? t("nav.collapse") : t("nav.expand")}
              className={cn(
                "flex h-9 items-center gap-2.5 rounded-lg px-2 text-xs text-muted-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-foreground",
                expanded ? "w-full justify-start" : "w-9 justify-center",
              )}
            >
              {expanded ? <ChevronsLeft className="size-4 shrink-0" /> : <PanelLeft className="size-4 shrink-0" />}
              {expanded && <span>{t("nav.collapse")}</span>}
            </button>
          </div>
        </aside>

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div
            {...desktopDragRegionProps("deep")}
            className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3 md:hidden"
          >
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label={t("nav.menu")}
              className="-ml-1 inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <Menu className="size-5" />
            </button>
            <span className="text-sm font-semibold tracking-tight">Locus Agent</span>
            <div className="ml-auto flex items-center gap-1">
              <NotificationBell />
              {mobileAction}
            </div>
          </div>
          <main className="relative min-w-0 flex-1 overflow-hidden bg-background">
            <div className="pointer-events-none absolute right-3 top-3 z-[70] hidden md:block">
              <NotificationBell menuAlign="end" className="pointer-events-auto" />
            </div>
            <Suspense fallback={<RouteFallback />}>
              <Outlet />
            </Suspense>
          </main>
        </div>
      </div>
    </ShellContext.Provider>
  );
}

function NavGroupDivider({ expanded }: { expanded: boolean }) {
  return (
    <div className={sidebarNavGroupDividerClass(expanded)} aria-hidden>
      <div className={sidebarNavGroupDividerLineClass(expanded)} />
    </div>
  );
}

function NavRow({
  to,
  labelKey,
  icon: Icon,
  basePrefix,
  expanded,
  onNavigate,
}: NavEntry & { basePrefix: string; expanded: boolean; onNavigate: () => void }) {
  const { t } = useTranslation();
  const label = t(labelKey);
  return (
    <NavLink
      to={`${basePrefix}${to}`}
      title={label}
      onClick={onNavigate}
      className={({ isActive }) => sidebarNavRowClass(isActive, expanded)}
    >
      <span className={sidebarNavIconSlotClass} aria-hidden>
        <Icon className={sidebarNavIconClass} strokeWidth={1.75} />
      </span>
      <span className={sidebarNavLabelClass(expanded)}>{label}</span>
    </NavLink>
  );
}

function RouteFallback() {
  return (
    <div className="flex h-full items-center justify-center">
      <span className="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
    </div>
  );
}
