# AgentPod Web

AgentPod 管理端 SPA：对话、技能、MCP、记忆、产物、定时任务、环境变量与账户设置。

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

## 构建与部署

生产构建产物输出到 `host/src/agentpod_host/web/spa`，由 Host FastAPI 托管：

```bash
npm run build
```

Docker 部署时 Host 镜像多阶段构建会自动执行 `npm ci && npm run build`。改前端后执行：

```bash
./rebuild.sh host
```

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
├── app/          # AppShell、Auth、Theme、工作区路由
├── routes/       # LoginRoute、ChatRoute
├── api/          # REST/SSE 客户端
├── features/     # 各功能模块
└── components/   # 通用 UI 组件
```
