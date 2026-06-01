import { lazy, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import "./index.css";
import { ToastProvider } from "@/components/ui/toast";
import { DialogProvider } from "@/components/ui/dialogs";
import { AuthProvider } from "@/app/auth";
import { NotificationProvider } from "@/features/notifications/NotificationProvider";
import { ThemeProvider } from "@/app/theme";
import { AppShell } from "@/app/AppShell";
import { LoginRoute } from "@/routes/LoginRoute";

const ChatRoute = lazy(() => import("@/routes/ChatRoute").then((m) => ({ default: m.ChatRoute })));
const SkillsRoute = lazy(() =>
  import("@/features/skills/SkillsRoute").then((m) => ({ default: m.SkillsRoute })),
);
const ToolsRoute = lazy(() =>
  import("@/features/tools/ToolsRoute").then((m) => ({ default: m.ToolsRoute })),
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

const shellChildren = [
  { index: true, element: <Navigate to="chat" replace /> },
  { path: "chat/:sessionId", element: <ChatRoute /> },
  { path: "chat", element: <ChatRoute /> },
  { path: "workspaces", element: <WorkspacesRoute /> },
  { path: "tools", element: <ToolsRoute /> },
  { path: "skills", element: <SkillsRoute /> },
  { path: "mcp", element: <McpRoute /> },
  { path: "memory", element: <MemoryRoute /> },
  { path: "scheduled-tasks", element: <ScheduledTasksRoute /> },
  { path: "env-vars", element: <EnvVarsRoute /> },
  { path: "artifacts", element: <ArtifactsRoute /> },
  { path: "artifacts/manage", element: <ArtifactsRoute /> },
  { path: "artifacts/c/:categoryId", element: <ArtifactsRoute /> },
  { path: "*", element: <Navigate to="chat" replace /> },
];

const router = createBrowserRouter([
  { path: "/login", element: <LoginRoute /> },
  {
    path: "/",
    element: (
      <AuthProvider>
        <NotificationProvider>
          <AppShell />
        </NotificationProvider>
      </AuthProvider>
    ),
    children: shellChildren,
  },
  {
    path: "/w/:workspaceId",
    element: (
      <AuthProvider>
        <NotificationProvider>
          <AppShell />
        </NotificationProvider>
      </AuthProvider>
    ),
    children: shellChildren,
  },
]);

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
