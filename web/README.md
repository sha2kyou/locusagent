# AgentPod Web

AgentPod 管理端 SPA：对话、技能、MCP、记忆、产物、定时任务、环境变量与账户设置。

## 架构

图例：`──→` 请求流向，`├─` 分流

```
【本地开发】npm run dev

浏览器 → Vite :5173
           ├─ 页面 → 热更新
           └─ /api · /health → 代理 Host :8080

【在线部署】Docker

浏览器 / PWA → Caddy :1223
                 ├─ 页面 → web 容器 · dist-web（npm run build）
                 └─ API  → Host :8080

macOS 桌面 → Gateway :1420 · dist-desktop（不经 web 容器）
                 └─ API  → Caddy :1223 → Host

详见根目录 [`README.md`](../README.md#架构概览) 与 [`desktop/README.md`](../desktop/README.md)。
```

## 技术栈

- React 19 + TypeScript + Vite 8
- Tailwind CSS 4
- `@assistant-ui/react` 对话 UI
- `react-router-dom` v7

## 本地开发

```bash
npm install
npm run dev
```

默认 `http://127.0.0.1:5173`，`/api` 与 `/health` 代理到 Host（`API_TARGET`，默认 `127.0.0.1:8080`）。

需先启动 Host（及 Agent 容器，若测试完整对话流程）：

```bash
# 仓库根目录
uv sync
uv run uvicorn agentpod_host.main:app --reload --port 8080
```

## 构建

| 命令 | 产物 | 用途 |
|------|------|------|
| `npm run build` | `dist-web/` | Docker 在线 Web 服务（含 PWA） |
| `npm run build:desktop` | `dist-desktop/` | macOS 桌面应用内嵌（无 PWA） |

桌面壳构建见仓库根目录 `./build-desktop.sh`。

## 部署（Docker）

在线页面由 **web** 容器（nginx 静态托管）提供，**Host 仅负责 API**。架构见上文「在线部署」；改前端后：

```bash
./rebuild.sh host
```

浏览器访问 `http://localhost:1223`（或 `PUBLIC_BASE_URL` 配置的地址）。

桌面应用使用 `dist-desktop/`，由 Tauri gateway 托管，不走 web 容器；变更后执行 `./build-desktop.sh`。

## 通知

- **Web / 桌面共用**：`NotificationProvider` 经 WebSocket 同步通知中心，新消息弹出应用内 sticky toast，铃铛可查看未读列表。
- **仅桌面**：同一新消息额外调用 macOS 系统通知（`src/lib/desktop-notification.ts`），不替代 toast。

## 路由

| 路径 | 功能 |
|------|------|
| `/login` | GitHub OAuth 登录 |
| `/chat[/:sessionId]` | 对话（SSE 流式） |
| `/skills` | 技能 CRUD |
| `/mcp` | MCP 配置 |
| `/memory` | 长期记忆 |
| `/artifacts` | 产物浏览 |
| `/scheduled-tasks` | 定时任务 |
| `/env-vars` | 环境变量 |
| `/workspaces` | 工作区切换 |

非默认工作区 URL 前缀：`/w/{workspaceId}/...`

## 鉴权

- `AuthProvider` 启动时拉取 `/api/me`；未登录自动跳转 `/login`
- API 请求带 `credentials: "same-origin"` 与 `X-Workspace-Id` 头
- 401 响应统一跳转登录页

## 目录结构

```
src/
├── app/          # AppShell、Auth、Theme、工作区路由、桌面标题栏
├── routes/       # LoginRoute、ChatRoute
├── api/          # REST/SSE 客户端
├── features/     # 各功能模块（含 notifications/）
├── lib/          # desktop-app.ts、desktop-notification.ts 等
└── components/   # 通用 UI 组件
```
