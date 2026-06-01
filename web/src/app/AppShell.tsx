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
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ArtifactsNav } from "@/features/artifacts/ArtifactsNav";
import { useAuth } from "./auth";
import { BrandMark } from "./Brand";
import { ApiKeyFlashModal, SettingsModal } from "@/features/settings/SettingsModal";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { flashApiKey, listWorkspaces } from "@/api/endpoints";
import type { WorkspaceItem } from "@/api/types";
import { stripWorkspacePrefix, withWorkspacePrefix } from "./workspace-route";

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
  { to: "/tools", label: "工具", icon: Wrench },
];
// 上下文与密钥
const NAV_CONTEXT: NavEntry[] = [
  { to: "/workspaces", label: "工作区", icon: FolderOpen },
  { to: "/memory", label: "记忆", icon: Brain },
  { to: "/env-vars", label: "环境变量", icon: KeyRound },
];
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
      <div className="flex h-full">
        {/* 移动端遮罩 */}
        {navOpen && (
          <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setNavOpen(false)} />
        )}

        {/* 图标导航轨（移动端为抽屉） */}
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col border-r border-sidebar-border bg-sidebar transition-transform duration-200",
            navOpen ? "translate-x-0" : "-translate-x-full",
            "md:static md:z-auto md:translate-x-0 md:transition-[width]",
            expanded ? "md:w-[208px]" : "md:w-[68px]",
          )}
        >
          <div className={cn("flex h-14 items-center gap-2.5 px-4", !expanded && "md:justify-center md:px-2")}>
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
              {expanded ? (
                <BrandMark />
              ) : (
                <>
                  <span className="md:hidden">
                    <BrandMark />
                  </span>
                  <NotificationBell className="hidden md:block" menuAlign="start" />
                </>
              )}
            </div>
            <span className={cn("min-w-0 flex-1 truncate text-[15px] font-semibold tracking-tight", !expanded && "md:hidden")}>
              AgentPod
            </span>
            <NotificationBell className={cn("hidden md:block", !expanded && "md:hidden")} menuAlign="start" />
          </div>

          <nav
            ref={navListRef}
            className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3 py-2"
          >
            {NAV_PRIMARY.map((item) => (
              <NavRow
                key={item.to}
                {...item}
                basePrefix={workspacePrefix}
                expanded={expanded}
                onNavigate={() => setNavOpen(false)}
              />
            ))}
            <ArtifactsNav basePrefix={workspacePrefix} expanded={expanded} onNavigate={() => setNavOpen(false)} />

            <div className="mx-1 my-1.5 border-t border-sidebar-border/70" />

            {NAV_CAPABILITIES.map((item) => (
              <NavRow
                key={item.to}
                {...item}
                basePrefix={workspacePrefix}
                expanded={expanded}
                onNavigate={() => setNavOpen(false)}
              />
            ))}

            <div className="mx-1 my-1.5 border-t border-sidebar-border/70" />

            {NAV_CONTEXT.map((item) => (
              <NavRow
                key={item.to}
                {...item}
                basePrefix={workspacePrefix}
                expanded={expanded}
                onNavigate={() => setNavOpen(false)}
              />
            ))}

            <div className="mx-1 my-1.5 border-t border-sidebar-border/70" />

            {NAV_AUTOMATION.map((item) => (
              <NavRow
                key={item.to}
                {...item}
                basePrefix={workspacePrefix}
                expanded={expanded}
                onNavigate={() => setNavOpen(false)}
              />
            ))}
          </nav>

          {/* 底部：agent 状态 + 用户 */}
          <div
            ref={menuRootRef}
            className={cn(
              "relative shrink-0 p-3",
              menuScrollable && "border-t border-sidebar-border/90 bg-sidebar shadow-[0_-10px_16px_-12px_rgba(2,6,23,0.8)]",
            )}
          >
            {!isDefaultWorkspace && (
              <div
                className={cn(
                  "mb-2 inline-flex w-fit max-w-full items-center gap-1.5 self-center rounded-md border border-border/70 bg-surface/60 px-2 py-1 text-[11px] text-muted-foreground",
                  expanded && "justify-center",
                  !expanded && "md:justify-center md:px-1 md:py-1",
                )}
                title={currentWorkspace?.description || currentWorkspaceLabel}
              >
                <span className={cn("max-w-full wrap-break-word text-center leading-4 whitespace-normal", !expanded && "md:hidden")}>
                  {currentWorkspaceLabel}
                </span>
                {!expanded && <span className="hidden md:block">WS</span>}
              </div>
            )}
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg p-1.5 transition-colors hover:bg-sidebar-accent/60",
                !expanded && "md:justify-center",
              )}
              title="账户"
            >
              <Avatar me={me} />
              <span className={cn("min-w-0 flex-1 text-left", !expanded && "md:hidden")}>
                <span className="block truncate text-sm font-medium">{me?.username ?? "—"}</span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {typeof me?.id === "number" ? `#${me.id}` : "#—"}
                </span>
              </span>
            </button>

            {menuOpen && (
              <>
                <div className="absolute bottom-16 left-3 right-3 z-20 overflow-hidden rounded-lg border border-border-strong bg-popover py-1 shadow-2xl apod-enter-up">
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      setSettingsOpen(true);
                    }}
                    className={cn(
                      "flex w-full items-center gap-2.5 px-3 py-2 text-sm hover:bg-secondary",
                      !expanded && "md:justify-center",
                    )}
                    title="设置"
                  >
                    <Settings className="size-4 shrink-0" />
                    <span className={cn(!expanded && "md:hidden")}>设置</span>
                  </button>
                  <div className="my-1 border-t border-border" />
                  <form action="/api/oauth/github/logout" method="post">
                    <button
                      type="submit"
                      className={cn(
                        "flex w-full items-center gap-2.5 px-3 py-2 text-sm text-destructive hover:bg-destructive/10",
                        !expanded && "md:justify-center",
                      )}
                      title="退出"
                    >
                      <LogOut className="size-4 shrink-0" />
                      <span className={cn(!expanded && "md:hidden")}>退出</span>
                    </button>
                  </form>
                </div>
              </>
            )}
          </div>

          {/* 收起按钮：仅桌面 */}
          <div className="hidden shrink-0 border-t border-sidebar-border p-2 md:block">
            <Button
              variant="ghost"
              size="icon-sm"
              className={cn(
                "w-full gap-2.5 px-2.5 text-muted-foreground",
                expanded ? "justify-start" : "justify-center",
              )}
              onClick={() => setExpanded((v) => !v)}
              title={expanded ? "收起" : "展开"}
            >
              {expanded ? <ChevronsLeft className="size-4" /> : <PanelLeft className="size-4" />}
              {expanded && <span className="text-xs">收起</span>}
            </Button>
          </div>
        </aside>

        {/* 主区 */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* 移动端顶栏 */}
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3 md:hidden">
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
          <main className="min-w-0 flex-1 overflow-hidden">
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
      className={({ isActive }) =>
        cn(
          "group relative flex h-10 items-center gap-3 rounded-lg px-2.5 text-sm font-medium transition-colors",
          !expanded && "md:justify-center",
          isActive
            ? "bg-sidebar-accent text-foreground"
            : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
        )
      }
    >
      <Icon className="size-[18px] shrink-0" />
      <span className={cn("truncate", !expanded && "md:hidden")}>{label}</span>
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
