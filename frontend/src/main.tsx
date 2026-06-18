import { lazy, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from "react-router-dom";
import { stripWorkspacePrefix, withWorkspacePrefix } from "@/app/workspace-route";
import { installExternalLinkHandling } from "@/lib/open-external";
import { ensureI18nReady } from "@/i18n";
import "./index.css";
import { ToastProvider, NullToastProvider } from "@/components/ui/toast";
import { DialogProvider } from "@/components/ui/dialogs";
import { AuthProvider } from "@/app/auth";
import { AppLocaleProvider } from "@/lib/use-app-locale";
import { AppTimezoneProvider } from "@/lib/use-app-timezone";
import { NotificationProvider } from "@/features/notifications/NotificationProvider";
import { ThemeProvider } from "@/app/theme";
import { AppShell } from "@/app/AppShell";
import { ChatRoute } from "@/routes/ChatRoute";
import { QuickChatRoute } from "@/routes/QuickChatRoute";
const SkillsRoute = lazy(() =>
  import("@/features/skills/SkillsRoute").then((m) => ({ default: m.SkillsRoute })),
);
const McpRoute = lazy(() => import("@/features/mcp/McpRoute").then((m) => ({ default: m.McpRoute })));
const WorkspacesRoute = lazy(() =>
  import("@/features/workspaces/WorkspacesRoute").then((m) => ({ default: m.WorkspacesRoute })),
);
const MemoryRoute = lazy(() =>
  import("@/features/memory/MemoryRoute").then((m) => ({ default: m.MemoryRoute })),
);
const EnvVarsRoute = lazy(() =>
  import("@/features/envvars/EnvVarsRoute").then((m) => ({ default: m.EnvVarsRoute })),
);
const ScheduledTasksRoute = lazy(() =>
  import("@/features/scheduled/ScheduledTasksRoute").then((m) => ({ default: m.ScheduledTasksRoute })),
);
const ArtifactsRoute = lazy(() =>
  import("@/features/artifacts/ArtifactsRoute").then((m) => ({ default: m.ArtifactsRoute })),
);
const SettingsRoute = lazy(() =>
  import("@/features/settings/SettingsRoute").then((m) => ({ default: m.SettingsRoute })),
);
const SettingsGeneralPage = lazy(() =>
  import("@/features/settings/SettingsGeneralPage").then((m) => ({ default: m.SettingsGeneralPage })),
);
const SettingsModelsPage = lazy(() =>
  import("@/features/settings/SettingsModelsPage").then((m) => ({ default: m.SettingsModelsPage })),
);
const SettingsUsagePage = lazy(() =>
  import("@/features/settings/UsageSummaryCard").then((m) => ({ default: m.SettingsUsageRoute })),
);
const SettingsToolsPage = lazy(() =>
  import("@/features/settings/SettingsToolsPage").then((m) => ({ default: m.SettingsToolsPage })),
);
const SettingsLogsPage = lazy(() =>
  import("@/features/settings/SettingsLogsPage").then((m) => ({ default: m.SettingsLogsPage })),
);
const SettingsDeveloperPage = lazy(() =>
  import("@/features/settings/SettingsDeveloperPage").then((m) => ({ default: m.SettingsDeveloperPage })),
);
const SettingsQuickChatPage = lazy(() =>
  import("@/features/settings/SettingsQuickChatPage").then((m) => ({ default: m.SettingsQuickChatPage })),
);
const SettingsIndexRedirect = lazy(() =>
  import("@/features/settings/SettingsRoute").then((m) => ({ default: m.SettingsIndexRedirect })),
);

function ArtifactsManageRedirect() {
  const location = useLocation();
  const { workspaceId } = stripWorkspacePrefix(location.pathname);
  return <Navigate to={withWorkspacePrefix("/artifacts", workspaceId)} replace />;
}

function ChatFallbackRedirect() {
  const location = useLocation();
  const { workspaceId } = stripWorkspacePrefix(location.pathname);
  return <Navigate to={withWorkspacePrefix("/chat", workspaceId)} replace />;
}

const shellChildren = [
  { index: true, element: <Navigate to="chat" replace /> },
  { path: "chat/:sessionId", element: <ChatRoute /> },
  { path: "chat", element: <ChatRoute /> },
  { path: "workspaces", element: <WorkspacesRoute /> },
  { path: "skills", element: <SkillsRoute /> },
  { path: "mcp", element: <McpRoute /> },
  { path: "memory", element: <MemoryRoute /> },
  { path: "scheduled-tasks", element: <ScheduledTasksRoute /> },
  { path: "env-vars", element: <EnvVarsRoute /> },
  { path: "artifacts", element: <ArtifactsRoute /> },
  { path: "artifacts/manage", element: <ArtifactsManageRedirect /> },
  { path: "artifacts/c/:categoryId", element: <ArtifactsRoute /> },
  {
    path: "settings",
    element: <SettingsRoute />,
    children: [
      { index: true, element: <SettingsIndexRedirect /> },
      { path: "general", element: <SettingsGeneralPage /> },
      { path: "models", element: <SettingsModelsPage /> },
      { path: "tools", element: <SettingsToolsPage /> },
      { path: "usage", element: <SettingsUsagePage /> },
      { path: "logs", element: <SettingsLogsPage /> },
      { path: "quick-chat", element: <SettingsQuickChatPage /> },
      { path: "developer", element: <SettingsDeveloperPage /> },
    ],
  },
  { path: "*", element: <ChatFallbackRedirect /> },
];

const router = createBrowserRouter([
  {
    path: "/quick-chat/:sessionId",
    element: (
      <AuthProvider>
        <AppLocaleProvider>
          <AppTimezoneProvider>
            <ThemeProvider>
              <NullToastProvider>
                <QuickChatRoute />
              </NullToastProvider>
            </ThemeProvider>
          </AppTimezoneProvider>
        </AppLocaleProvider>
      </AuthProvider>
    ),
  },
  {
    path: "/quick-chat",
    element: (
      <AuthProvider>
        <AppLocaleProvider>
          <AppTimezoneProvider>
            <ThemeProvider>
              <NullToastProvider>
                <QuickChatRoute />
              </NullToastProvider>
            </ThemeProvider>
          </AppTimezoneProvider>
        </AppLocaleProvider>
      </AuthProvider>
    ),
  },
  {
    path: "/",
    element: (
      <AuthProvider>
        <AppLocaleProvider>
          <AppTimezoneProvider>
            <NotificationProvider>
              <AppShell />
            </NotificationProvider>
          </AppTimezoneProvider>
        </AppLocaleProvider>
      </AuthProvider>
    ),
    children: shellChildren,
  },
  {
    path: "/w/:workspaceId",
    element: (
      <AuthProvider>
        <AppLocaleProvider>
          <AppTimezoneProvider>
            <NotificationProvider>
              <AppShell />
            </NotificationProvider>
          </AppTimezoneProvider>
        </AppLocaleProvider>
      </AuthProvider>
    ),
    children: shellChildren,
  },
]);

installExternalLinkHandling();

void ensureI18nReady().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ThemeProvider>
        <ToastProvider>
          <DialogProvider>
            <RouterProvider router={router} />
          </DialogProvider>
        </ToastProvider>
      </ThemeProvider>
    </StrictMode>,
  );
});
