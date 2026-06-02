# AgentPod

自托管 AI Agent 平台：GitHub 登录、每用户独立 Docker 容器、OpenAI 兼容 API、内置 Skills / MCP / Memory，支持 MCP OAuth 与 PWA 安装。

## 项目目标

- 对外提供标准 OpenAI 风格接口（`/api/v1/*`）。
- 对内提供可视化工作台（见下表）。
- 通过容器隔离保证多用户运行与数据隔离。

### 工作台路由

| 路径 | 功能 |
|------|------|
| `/chat` | 对话（SSE 流式、附件、会话管理） |
| `/skills` | 技能库（公共 / 私有） |
| `/mcp` | MCP 服务配置、OAuth 授权、连接测试 |
| `/memory` | 长期记忆 |
| `/workspaces` | 多工作区切换 |
| `/env-vars` | 工作区环境变量 |
| `/scheduled-tasks` | 定时任务 |
| `/artifacts` | 制品库（分类与内容） |

工作区非默认时 URL 前缀为 `/w/{workspace_id}/...`。侧栏「工具」开关页（`/tools`）已实现但默认未开放入口。

## 架构概览

```
[入口层]
浏览器 / PWA · 外部 API 客户端
                │
                ▼
        Caddy (反向代理, SSE 透传, Docker DNS)

[控制平面 Host: FastAPI + PostgreSQL + Redis]
├── GitHub OAuth / Session
├── MCP OAuth（凭据加密存库，/api/oauth/mcp）
├── API 网关
│   ├── /api/v1/*                                (Bearer 鉴权)
│   └── /api/workspace/* /api/me* /api/settings/* (Session 鉴权)
├── Orchestrator                                  (容器生命周期管理)
├── 内部代理（/internal/llm、embedding、tavily、jina 等）
├── 通知 WebSocket
└── PostgreSQL（用户 / 工作区 / MCP OAuth 凭据等）
                │
                │ X-Internal-Token + X-Workspace-Id
                ▼
[执行平面 Agent: 每用户独立容器]
├── /v1/* /workspace/*                            (内部鉴权入口)
├── Chat Loop + Run Manager                       (Tool Dispatch + SSE)
├── Tool Registry                                 (builtin + MCP 动态工具)
└── SQLite + sqlite-vec                           (sessions / messages / memory / runs)
                │
                ├── shared-skills（公共技能库）
                └── TEI Embedding（经 Host 代理）
```

**MCP 连接策略（Agent）**：只读接口（如列会话）不阻塞 MCP 全量连接；对话与 MCP 管理在需要时再连接。HTTP MCP 的 OAuth 凭据由 Host 保存，Agent 用 Bearer + Host 刷新 token，不在容器内走浏览器授权。

## 快速开始（推荐路径）

### 1) 准备依赖

- Python 3.11+
- `uv`
- Docker + Docker Compose

### 2) 初始化环境变量

```bash
cp .env.example .env
openssl rand -base64 32
```

将生成值写入 `.env` 的 `ENCRYPTION_KEY` 和 `SESSION_SECRET`。

至少补齐：

| 变量 | 说明 |
|------|------|
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub 登录 |
| `OAUTH_REDIRECT_URI` | GitHub 回调（与对外访问域名一致） |
| `MCP_OAUTH_REDIRECT_URI` | MCP OAuth 回调，如 `http://localhost:1223/api/oauth/mcp/callback` |
| `ENCRYPTION_KEY` / `SESSION_SECRET` | 加密与 Session |
| `DB_PASSWORD` | 与 `DATABASE_URL` 中密码一致 |
| `LLM_API_KEY` | 及 `LLM_MODEL`、辅助模型等（见 `.env.example`） |
| `PUBLIC_BASE_URL` | 对外根 URL（OAuth 与链接生成） |

首次部署后 Host 会执行数据库迁移（含 `mcp_oauth_credentials` 表）。

### 3) 启动整套服务

```bash
docker compose up -d --build
docker build -f "agent/Dockerfile" -t "agentpod-agent:latest" "."
```

默认入口：`http://localhost:1223`（以 `docker-compose.yml` / Caddy 映射为准）。

## 启动后验证

### 健康检查

```bash
curl "http://localhost:1223/health"
curl "http://localhost:1223/api/v1/health"
```

### 首次使用

1. 浏览器打开站点，使用 GitHub 登录。
2. 进入 `/chat` 发起对话（模型由 Host `.env` 注入，无需在 UI 填写 API Key）。
3. 可选：在 `/mcp` 添加 HTTP MCP；需 OAuth 时在服务配置中选 OAuth，或在 `mcp.yaml` 中写 `auth: oauth` 后于页面完成授权。

### 外部 API（Bearer）

设置中可查看/轮换 `agent_api_key`，然后：

```bash
curl "http://localhost:1223/api/v1/models" \
  -H "Authorization: Bearer <agent_api_key>"
```

## MCP OAuth 说明

- **UI 新建** HTTP MCP：默认认证方式为 OAuth。
- **手写 `mcp.yaml`**：未写 `auth` 的 HTTP 服务为直连（`none`）；需要 OAuth 时显式添加：

```yaml
servers:
  - name: notion
    transport: http
    url: https://mcp.notion.com/mcp
    auth: oauth
```

- 授权流程：MCP 页点击连接 → Host 跳转提供商 → 回调后 Agent 自动重连该服务。
- `MCP_OAUTH_REDIRECT_URI` 必须与浏览器实际访问的 Host 地址一致。

## PWA

前端启用 `vite-plugin-pwa`：可「添加到主屏幕」，静态资源离线缓存；**不缓存** `/api`、`/health` 请求。

- 图标源文件：`web/public/app-icon.svg`
- 重新导出 PNG：`cd web && npm run icons`
- 更新后需 `./rebuild.sh host` 并强刷浏览器（必要时清除旧 Service Worker）

## 本地开发（不走 compose）

```bash
uv sync

# Host（8080）
uv run uvicorn agentpod_host.main:app --reload --port 8080

# Agent（8000，另开终端）
uv run uvicorn agentpod_agent.main:app --reload --port 8000
```

前端：

```bash
cd web
npm install
npm run dev    # 默认 http://127.0.0.1:5173，/api 代理到 Host
npm run build  # 产物写入 host/.../web/spa
```

## 按需重建

原则：**只重建受影响层**。详见仓库根目录 `CLAUDE.md` 与 `rebuild.sh`。

| 变更范围 | 命令 |
|----------|------|
| `web/` 或 `host/` | `./rebuild.sh host`（含 SPA 构建，并 **restart caddy**） |
| `agent/` | `./rebuild.sh agent <user_id>` |
| host + agent 镜像 | `./rebuild.sh full [user_id]` |
| postgres / tei 等 | `./rebuild.sh infra`（仅在基础设施异常时使用） |

`agent` 镜像使用 `docker build`，不走 `compose build`。未给出 `user_id` 时不要批量重建所有用户容器。

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | rg "apod-user|agentpod-host"
```

## 鉴权与路由边界

- **Bearer** 仅允许：`/api/v1/chat/completions`、`/api/v1/responses`、`/api/v1/models`、`/api/v1/health`
- **Session** 用于：`/api/workspace/*`、`/api/me*`、`/api/settings/*`、OAuth 浏览器流程等
- `agent_api_key` 访问 `/api/workspace/*` → `403`
- Session 访问 `/api/v1/*` → `403`

## 目录结构

```
.
├── pyproject.toml          # uv workspace 根
├── docker-compose.yml
├── Caddyfile
├── rebuild.sh
├── host/                   # 控制平面
│   ├── Dockerfile
│   └── src/agentpod_host/
├── agent/                  # 执行平面
│   ├── Dockerfile
│   └── src/agentpod_agent/
├── web/                    # React SPA（Vite，构建进 host 镜像）
│   ├── public/             # favicon、PWA 图标等
│   └── src/
└── shared-skills/          # 公共技能库
```

## 常见问题

| 现象 | 处理 |
|------|------|
| `503` + `Retry-After` | 用户 Agent 容器冷启动，稍后重试 |
| 对话无输出 / SSE 卡住 | 检查 Caddy 未缓冲 SSE；见 `Caddyfile` |
| `/api/workspace/*` 返回 `403` | 使用了 Bearer 而非浏览器 Session |
| Host 重建后偶发 `502` | 执行 `./rebuild.sh host`（会 restart caddy） |
| MCP 显示已授权但离线 | MCP 页点「重连」；或等待后台预热后刷新列表 |
| OAuth 后仍连不上 | 确认 `MCP_OAUTH_REDIRECT_URI`、yaml 中 `auth: oauth` |
| PWA 异常 / 旧页面 | 强刷或清除站点数据；确认未把 `node_modules` 放进 `web/public/` |
| 登录后无法对话 | 检查 Host `.env` 中 `LLM_API_KEY`、`LLM_MODEL` |

## P0 验收标准（DoD）

- 新用户首次登录 10s 内进入工作台，首轮对话首包 30s 内返回（需已配置 `LLM_API_KEY`）。
- `/api/v1/chat/completions`、`/api/v1/responses`、`/api/v1/models` 鉴权通过；冷启动返回 `503 + Retry-After`。
- `agent_api_key` 访问 `/api/workspace/*` 一律 `403`；Session 访问 `/api/v1/*` 一律 `403`。
- 用户 A 容器从网络层无法访问用户 B 容器。
- 容器以 `uid=10001`、`cap_drop=ALL`、`read_only=true` 启动。
- 日志不出现明文密钥；业务容器无 `docker.sock` 挂载。
- SSE：首包 &lt; 1s（不含 LLM），chunk 间隔 &lt; 200ms。
