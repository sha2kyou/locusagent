import { createContext, Suspense, useContext, useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Blocks,
  Brain,
  ChevronsLeft,
  Clock,
  LogOut,
  Menu,
  MessagesSquare,
  PanelLeft,
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
import { flashApiKey } from "@/api/endpoints";

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
  { to: "/mcp", label: "MCP", icon: Blocks },
  { to: "/tools", label: "工具", icon: Wrench },
];
// 上下文与密钥
const NAV_CONTEXT: NavEntry[] = [
  { to: "/memory", label: "记忆", icon: Brain },
  { to: "/env-vars", label: "环境变量", icon: KeyRound },
];
// 自动化：独立展示于配置组下方
const NAV_AUTOMATION: NavEntry[] = [{ to: "/scheduled-tasks", label: "定时任务", icon: Clock }];

const EXPAND_KEY = "apod-nav-expanded";

export function AppShell() {
  const { me, readiness } = useAuth();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(
    () => localStorage.getItem(EXPAND_KEY) !== "0",
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [flashKey, setFlashKey] = useState<string | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [mobileAction, setMobileAction] = useState<ReactNode>(null);
  const forceModelSetup = !!me && !me.llm_configured;

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

  // 首次进入未配置模型时自动打开设置
  useEffect(() => {
    if (me && !me.llm_configured) setSettingsOpen(true);
  }, [me]);

  const toneColor =
    readiness.tone === "ready"
      ? "bg-success"
      : readiness.tone === "blocked"
        ? "bg-destructive"
        : "bg-warning";

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
              <BrandMark />
            </div>
            <span className={cn("min-w-0 flex-1 truncate text-[15px] font-semibold tracking-tight", !expanded && "md:hidden")}>
              AgentPod
            </span>
            <NotificationBell className={cn(!expanded && "md:hidden")} menuAlign="start" />
          </div>

          <nav className="flex flex-1 flex-col gap-1 px-3 py-2">
            {NAV_PRIMARY.map((item) => (
              <NavRow key={item.to} {...item} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}
            <ArtifactsNav expanded={expanded} onNavigate={() => setNavOpen(false)} />

            <div className="mx-1 my-1.5 border-t border-sidebar-border/70" />

            {NAV_CAPABILITIES.map((item) => (
              <NavRow key={item.to} {...item} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}

            <div className="mx-1 my-1.5 border-t border-sidebar-border/70" />

            {NAV_CONTEXT.map((item) => (
              <NavRow key={item.to} {...item} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}

            <div className="mx-1 my-1.5 border-t border-sidebar-border/70" />

            {NAV_AUTOMATION.map((item) => (
              <NavRow key={item.to} {...item} expanded={expanded} onNavigate={() => setNavOpen(false)} />
            ))}
          </nav>

          {/* 底部：agent 状态 + 用户 */}
          <div className="relative p-3">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg p-1.5 transition-colors hover:bg-sidebar-accent/60",
                !expanded && "md:justify-center",
              )}
              title={`Agent ${readiness.label}`}
            >
              <Avatar me={me} />
              <span className={cn("min-w-0 flex-1 text-left", !expanded && "md:hidden")}>
                <span className="block truncate text-sm font-medium">{me?.username ?? "—"}</span>
                <span className="mt-1 inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] text-muted-foreground">
                  <span className={cn("size-1.5 shrink-0 rounded-full", toneColor)} />
                  <span className="truncate">Agent · {readiness.label}</span>
                </span>
              </span>
            </button>

            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
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
          <div className="hidden border-t border-sidebar-border p-2 md:block">
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
        required={forceModelSetup}
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
  expanded,
  onNavigate,
}: NavEntry & { expanded: boolean; onNavigate: () => void }) {
  return (
    <NavLink
      to={to}
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
