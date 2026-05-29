import { createContext, Suspense, useContext, useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Blocks,
  Brain,
  ChevronsLeft,
  LogOut,
  Menu,
  MessagesSquare,
  PanelLeft,
  Settings,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuth } from "./auth";
import { BrandMark } from "./Brand";
import { ApiKeyFlashModal, SettingsModal } from "@/features/settings/SettingsModal";
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

const NAV = [
  { to: "/chat", label: "对话", icon: MessagesSquare },
  { to: "/skills", label: "技能", icon: Sparkles },
  { to: "/mcp", label: "MCP", icon: Blocks },
  { to: "/memory", label: "记忆", icon: Brain },
];

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
            <span className={cn("truncate text-[15px] font-semibold tracking-tight", !expanded && "md:hidden")}>
              AgentPod
            </span>
          </div>

          <nav className="flex flex-1 flex-col gap-1 px-3 py-2">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                title={label}
                onClick={() => setNavOpen(false)}
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
                {({ isActive }) => (
                  <>
                    <span
                      className={cn(
                        "absolute left-0 h-5 w-0.5 rounded-full bg-brand transition-opacity",
                        isActive ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <Icon className="size-[18px] shrink-0" />
                    <span className={cn("truncate", !expanded && "md:hidden")}>{label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          {/* 底部：agent 状态 + 用户 */}
          <div className="relative border-t border-sidebar-border p-3">
            <div
              className={cn(
                "mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted-foreground",
                !expanded && "md:justify-center",
              )}
              title={`Agent ${readiness.label}`}
            >
              <span className={cn("size-2 shrink-0 rounded-full", toneColor)} />
              <span className={cn("truncate", !expanded && "md:hidden")}>{readiness.label}</span>
            </div>

            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg p-1.5 transition-colors hover:bg-sidebar-accent/60",
                !expanded && "md:justify-center",
              )}
            >
              <Avatar me={me} />
              <span className={cn("min-w-0 flex-1 text-left", !expanded && "md:hidden")}>
                <span className="block truncate text-sm font-medium">{me?.username ?? "—"}</span>
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
            <div className="ml-auto flex items-center">{mobileAction}</div>
          </div>
          <main className="min-w-0 flex-1 overflow-hidden">
            <Suspense fallback={<RouteFallback />}>
              <Outlet />
            </Suspense>
          </main>
        </div>
      </div>

      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} onLogout={() => navigate("/login")} />
      <ApiKeyFlashModal value={flashKey} onClose={() => setFlashKey(null)} />
    </ShellContext.Provider>
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
