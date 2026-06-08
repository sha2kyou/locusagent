# AgentPod Web

AgentPod 管理端 SPA：对话、技能、MCP、记忆、产物、定时任务、环境变量与账户设置。

## 架构

图例：`──→` 请求流向，`├─` 分流

```
【本地开发】npm run dev

浏览器 → Vite :5173
           ├─ 页面 → 热更新
           └─ /api · /health → 代理 Sidecar :8080

【macOS 桌面】AgentPod.app

浏览器 WebView → Gateway :1420 · dist-desktop
                 └─ /api · /health → Sidecar :8080（Python 单体 Host+Agent）

详见根目录 [`README.md`](../README.md) 与 [`desktop/README.md`](../desktop/README.md)。
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

默认 `http://127.0.0.1:5173`，`/api` 与 `/health` 代理到 Sidecar（`API_TARGET`，默认 `127.0.0.1:8080`）。

需先启动单体后端：

```bash
# 仓库根目录
./rebuild.sh sidecar
cd sidecar && source .venv/bin/activate
AGENTPOD_MONOLITH=1 uvicorn agentpod.main:app --reload --host 127.0.0.1 --port 8080
```

## 构建

| 命令 | 产物 | 用途 |
|------|------|------|
| `npm run build:desktop` | `dist-desktop/` | macOS 桌面应用内嵌 |

桌面壳构建见仓库根目录 `./rebuild.sh desktop`。

## 通知

- **Web / 桌面共用**：`NotificationProvider` 经 WebSocket 同步通知中心，新消息弹出应用内 sticky toast，铃铛可查看未读列表。
- **仅桌面**：同一新消息额外调用 macOS 系统通知（`src/lib/desktop-notification.ts`），不替代 toast。

## 路由

| 路径 | 功能 |
|------|------|
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

- `AuthProvider` 启动时拉取 `/api/me`；Host 自动签发 session，打开即用
- API 请求带 `credentials: "same-origin"` 与 `X-Workspace-Id` 头

## 目录结构

```
src/
├── app/          # AppShell、Auth、Theme、工作区路由、桌面标题栏
├── routes/       # ChatRoute
├── api/          # REST/SSE 客户端
├── features/     # 各功能模块（含 notifications/）
├── lib/          # desktop-app.ts、desktop-notification.ts 等
└── components/   # 通用 UI 组件
```
