import { createContext, Suspense, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Brain,
  ChevronsLeft,
  Clock,
  FolderOpen,
  LogOut,
  Menu,
  MessagesSquare,
  PanelLeft,
  Plug,
  KeyRound,
  Settings,
  Sparkles,
  // Wrench,
} from "lucide-react";
import { BrandMark } from "@/app/Brand";
import { DesktopWindowDragOverlay } from "@/app/DesktopTitlebarSpacer";
import { desktopDragRegionProps } from "@/lib/desktop-app";
import { cn } from "@/lib/utils";
import { ArtifactsNav } from "@/features/artifacts/ArtifactsNav";
import { useAuth } from "./auth";
import { ApiKeyFlashModal, SettingsModal } from "@/features/settings/SettingsModal";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { flashApiKey, listWorkspaces } from "@/api/endpoints";
import type { WorkspaceItem } from "@/api/types";
import { isChatRoutePath, stripWorkspacePrefix, withWorkspacePrefix } from "./workspace-route";
import {
  sidebarNavGroupLabelClass,
  sidebarNavIconClass,
  sidebarNavIconSlotClass,
  sidebarNavLabelClass,
  sidebarNavRowClass,
} from "./sidebar-nav-styles";

interface ShellApi {
  openSettings: () => void;
  /** 路由可注入移动端顶栏右侧操作（如会话抽屉开关） */
  setMobileAction: (node: ReactNode) => void;
}
const ShellContext = createContext<ShellApi | null>(null);
export function useShell() {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used within AppShell");
  return ctx;
}

type NavEntry = { to: string; label: string; icon: typeof MessagesSquare };

// 内容类：日常产出与消费
const NAV_PRIMARY: NavEntry[] = [{ to: "/chat", label: "对话", icon: MessagesSquare }];
// 能力扩展
const NAV_CAPABILITIES: NavEntry[] = [
  { to: "/skills", label: "技能", icon: Sparkles },
  { to: "/mcp", label: "MCP", icon: Plug },
  // { to: "/tools", label: "工具", icon: Wrench },
];
// 上下文与密钥
const NAV_CONTEXT: NavEntry[] = [
  { to: "/memory", label: "记忆", icon: Brain },
  { to: "/env-vars", label: "环境变量", icon: KeyRound },
];
const NAV_WORKSPACE: NavEntry = { to: "/workspaces", label: "工作区", icon: FolderOpen };
// 自动化：独立展示于配置组下方
const NAV_AUTOMATION: NavEntry[] = [{ to: "/scheduled-tasks", label: "定时任务", icon: Clock }];

const EXPAND_KEY = "apod-nav-expanded";

export function AppShell() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [expanded, setExpanded] = useState(
    () => localStorage.getItem(EXPAND_KEY) !== "0",
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [flashKey, setFlashKey] = useState<string | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [mobileAction, setMobileAction] = useState<ReactNode>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const menuRootRef = useRef<HTMLDivElement>(null);
  const navListRef = useRef<HTMLElement>(null);
  const [menuScrollable, setMenuScrollable] = useState(false);
  const defaultWorkspaceId = workspaces.find((w) => w.is_default)?.id ?? "";
  const currentWorkspace = workspaces.find((w) => w.id === me?.current_workspace_id) ?? null;
  const currentWorkspaceLabel = currentWorkspace?.name || "默认工作区";
  const isDefaultWorkspace = !!currentWorkspace && currentWorkspace.is_default;
  const routeWorkspace = stripWorkspacePrefix(location.pathname);
  const onChatRoute = isChatRoutePath(location.pathname);
  const workspacePrefix = me?.current_workspace_id && !isDefaultWorkspace ? `/w/${me.current_workspace_id}` : "";

  useEffect(() => {
    localStorage.setItem(EXPAND_KEY, expanded ? "1" : "0");
  }, [expanded]);

  // 新用户登录后一次性展示外部 API Key
  useEffect(() => {
    void flashApiKey()
      .then((r) => {
        if (r.api_key) setFlashKey(r.api_key);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!me) return;
    void listWorkspaces()
      .then((res) => setWorkspaces(res.items))
      .catch(() => setWorkspaces([]));
  }, [me?.id, me?.current_workspace_id]);

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

  useEffect(() => {
    if (!menuOpen) return;
    const onDocMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRootRef.current?.contains(target)) return;
      setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [menuOpen]);

  useEffect(() => {
    const el = navListRef.current;
    if (!el) return;
    const updateScrollable = () => {
      setMenuScrollable(el.scrollHeight > el.clientHeight + 1);
    };
    updateScrollable();
    const ro = new ResizeObserver(updateScrollable);
    ro.observe(el);
    window.addEventListener("resize", updateScrollable);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", updateScrollable);
    };
  }, [expanded, location.pathname, workspaces.length]);

  return (
    <ShellContext.Provider value={{ openSettings: () => setSettingsOpen(true), setMobileAction }}>
      <DesktopWindowDragOverlay
        mainOffsetClassName={expanded ? "left-0 md:left-[220px]" : "left-0 md:left-[60px]"}
      />
      <div className="flex h-full">
        {/* 移动端遮罩 */}
        {navOpen && (
          <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setNavOpen(false)} />
        )}

        {/* 左侧导航栏 */}
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-50 flex w-[265px] flex-col bg-sidebar transition-transform duration-200",
            navOpen ? "translate-x-0" : "-translate-x-full",
            "md:static md:z-auto md:translate-x-0 md:border-r md:border-sidebar-border md:transition-[width]",
            expanded ? "md:w-[220px]" : "md:w-[60px]",
          )}
        >
          {/* Header：布局与导航行一致，收起时仅隐藏标题 */}
          <div
            {...desktopDragRegionProps("deep")}
            className={cn(
              "apod-sidebar-header flex h-[52px] shrink-0 items-center px-2",
              !expanded && "md:justify-center md:px-0",
            )}
          >
            <div
              className={cn(
                "flex min-w-0 items-center gap-2 px-2",
                expanded ? "flex-1" : "md:justify-center md:px-0",
              )}
            >
              <span className="flex w-6 shrink-0 items-center justify-center">
                <BrandMark className="size-6 rounded-full" />
              </span>
              <span
                className={cn(
                  "min-w-0 text-[14px] font-bold leading-snug tracking-tight",
                  !expanded && "md:hidden",
                )}
              >
                AgentPod
              </span>
            </div>
          </div>

          {/* 导航列表 */}
          <nav
            ref={navListRef}
            className={cn(
              "flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-2",
              !expanded && "md:items-center md:px-0",
            )}
          >
            {NAV_PRIMARY.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}
            <ArtifactsNav basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            <NavRow {...NAV_WORKSPACE} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />

            <NavGroupLabel label="能力" expanded={expanded} />
            {NAV_CAPABILITIES.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}

            <NavGroupLabel label="数据" expanded={expanded} />
            {NAV_CONTEXT.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}

            <NavGroupLabel label="自动化" expanded={expanded} />
            {NAV_AUTOMATION.map((item) => (
              <NavRow key={item.to} {...item} basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}
          </nav>

          {/* 底部：用户入口 */}
          <div
            ref={menuRootRef}
            className={cn(
              "relative shrink-0 border-t border-sidebar-border/40 p-2.5",
              !expanded && "md:flex md:flex-col md:items-center md:p-2",
              menuScrollable && "bg-sidebar",
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
                <span className={cn("max-w-full truncate leading-4", !expanded && "md:hidden")}>
                  {currentWorkspaceLabel}
                </span>
                {!expanded && <span className="hidden md:block text-[10px]">WS</span>}
              </div>
            )}
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-sidebar-accent",
                !expanded && "md:size-9 md:justify-center md:px-0 md:py-0",
                menuOpen && "bg-sidebar-accent",
              )}
              title="账户"
            >
              <Avatar me={me} />
              <span className={cn("min-w-0 flex-1 text-left", !expanded && "md:hidden")}>
                <span className="block truncate text-[13px] font-semibold leading-tight">{me?.username ?? "—"}</span>
                <span className="mt-0.5 block truncate text-[11px] leading-tight text-muted-foreground/60">
                  {typeof me?.id === "number" ? `#${me.id}` : "—"}
                </span>
              </span>
            </button>

            {menuOpen && (
              <div className="absolute bottom-[calc(100%+6px)] left-2.5 right-2.5 z-20 overflow-hidden rounded-xl border border-border-strong bg-popover py-1.5 shadow-lg apod-enter-up">
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); setSettingsOpen(true); }}
                  className={cn(
                    "flex w-full items-center gap-2.5 px-3 py-2 text-[13px] transition-colors hover:bg-secondary",
                    !expanded && "md:justify-center",
                  )}
                >
                  <Settings className="size-4 shrink-0 text-muted-foreground" />
                  <span className={cn(!expanded && "md:hidden")}>设置</span>
                </button>
                <div className="mx-2 my-1 border-t border-border/50" />
                <form action="/api/oauth/github/logout" method="post">
                  <button
                    type="submit"
                    className={cn(
                      "flex w-full items-center gap-2.5 px-3 py-2 text-[13px] text-destructive transition-colors hover:bg-destructive/8",
                      !expanded && "md:justify-center",
                    )}
                  >
                    <LogOut className="size-4 shrink-0" />
                    <span className={cn(!expanded && "md:hidden")}>退出</span>
                  </button>
                </form>
              </div>
            )}
          </div>

          {/* 收起/展开：仅桌面，置于最底部 */}
          <div className={cn("hidden shrink-0 border-t border-sidebar-border/40 p-2 md:block", !expanded && "md:flex md:justify-center")}>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              title={expanded ? "收起" : "展开"}
              className={cn(
                "flex h-9 items-center gap-2.5 rounded-lg px-2 text-xs text-muted-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-foreground",
                expanded ? "w-full justify-start" : "w-9 justify-center",
              )}
            >
              {expanded ? <ChevronsLeft className="size-4 shrink-0" /> : <PanelLeft className="size-4 shrink-0" />}
              {expanded && <span>收起</span>}
            </button>
          </div>
        </aside>

        {/* 主区 */}
        <div className="relative flex min-w-0 flex-1 flex-col">
          {/* 移动端顶栏 */}
          <div
            {...desktopDragRegionProps("deep")}
            className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3 md:hidden"
          >
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="菜单"
              className="-ml-1 inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <Menu className="size-5" />
            </button>
            <span className="text-sm font-semibold tracking-tight">AgentPod</span>
            <div className="ml-auto flex items-center gap-1">
              <NotificationBell />
              {mobileAction}
            </div>
          </div>
          <main className="relative min-w-0 flex-1 overflow-hidden">
            {/* 桌面端：右上角浮动，不占布局高度 */}
            <div className="pointer-events-none absolute right-3 top-3 z-[70] hidden md:block">
              <NotificationBell menuAlign="end" className="pointer-events-auto" />
            </div>
            <Suspense fallback={<RouteFallback />}>
              <Outlet />
            </Suspense>
          </main>
        </div>
      </div>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onLogout={() => navigate("/login")}
      />
      <ApiKeyFlashModal value={flashKey} onClose={() => setFlashKey(null)} />
    </ShellContext.Provider>
  );
}

function NavGroupLabel({ label, expanded }: { label: string; expanded: boolean }) {
  return <div className={sidebarNavGroupLabelClass(expanded)}>{expanded ? label : null}</div>;
}

function NavRow({
  to,
  label,
  icon: Icon,
  basePrefix,
  expanded,
  onNavigate,
}: NavEntry & { basePrefix: string; expanded: boolean; onNavigate: () => void }) {
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

function Avatar({ me }: { me: { username: string; avatar_url: string | null } | null }) {
  const [failed, setFailed] = useState(false);
  const src = me?.avatar_url;
  const showImg = src && src.startsWith("https:") && !failed;
  if (showImg) {
    return (
      <img
        src={src}
        alt={me?.username}
        onError={() => setFailed(true)}
        className="size-8 shrink-0 rounded-full object-cover"
      />
    );
  }
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold uppercase text-muted-foreground">
      {me?.username?.[0] ?? "?"}
    </span>
  );
}
