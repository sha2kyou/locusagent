# AgentPod

自托管 AI Agent 平台：GitHub 登录、每用户独立 Docker 容器、OpenAI 兼容 API、内置 Skills/MCP/Memory。

## 项目目标

- 对外提供标准 OpenAI 风格接口（`/api/v1/*`）。
- 对内提供可视化工作台（`/chat`、`/skills`、`/mcp`、`/memory`）。
- 通过容器隔离保证多用户运行与数据隔离。

## 架构概览

```
[入口层]
浏览器用户 / 外部 API 客户端
                │
                ▼
        Caddy (反向代理, SSE 透传)

[控制平面 Host: FastAPI + PostgreSQL]
├── GitHub OAuth / Session
├── API 网关
│   ├── /api/v1/*                                (Bearer 鉴权)
│   └── /api/workspace/* /api/me* /api/settings/* (Session 鉴权)
├── Orchestrator                                  (容器生命周期管理)
├── Embedding Proxy                               (/internal/embedding/*)
└── PostgreSQL                                    (users / audit / metadata)
                │
                │ X-Internal-Token
                ▼
[执行平面 Agent: 每用户独立容器]
├── /v1/* /workspace/*                            (内部鉴权入口)
├── Chat Loop + Run Manager                       (Tool Dispatch + SSE)
├── Tool Registry                                 (builtin + MCP dynamic)
└── SQLite + sqlite-vec                           (sessions/messages/memory/runs)
                │
                ├── shared-skills (公共技能库)
                └── TEI Embedding 服务 (经 Host Proxy 访问)
```

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
至少补齐以下变量：

- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `ENCRYPTION_KEY`
- `SESSION_SECRET`
- `DB_PASSWORD`
- `LLM_API_KEY`（及可选的 `LLM_MODEL`、辅助模型变量，见 `.env.example`）

### 3) 启动整套服务

```bash
docker compose up -d --build
docker build -f "agent/Dockerfile" -t "agentpod-agent:latest" "."
```

默认入口：`http://localhost:1223`

## 启动后验证

### 健康检查

```bash
curl "http://localhost:1223/health"
curl "http://localhost:1223/api/v1/health"
```

### 首次使用路径

1. 浏览器打开 `http://localhost:1223`
2. 用 GitHub 登录
3. 打开 `http://localhost:1223/chat` 发起对话（模型由服务端 `.env` 注入）

### API 验证（Bearer）

拿到 `agent_api_key` 后可测试：

```bash
curl "http://localhost:1223/api/v1/models" \
  -H "Authorization: Bearer <agent_api_key>"
```

## 本地开发（不走 compose）

用于调试代码，不是推荐新手路径。

```bash
# 根目录同步依赖（host/agent 共用 .venv）
uv sync

# 启动 Host
uv run uvicorn agentpod_host.main:app --reload --port 8080

# 启动 Agent（另一个终端）
uv run uvicorn agentpod_agent.main:app --reload --port 8000
```

## Compose 下按需重建规则

原则：只重建受影响层，避免全量重建。

### 1) 前端（`web/`）

前端为独立的 React SPA（Vite + React + TypeScript + Tailwind v4 + assistant-ui）。**生产环境**：构建在 `host` 镜像内完成（多阶段 Docker），不再 volume 挂载。

```bash
cd web

# 本地开发
npm install
npm run dev   # 默认 http://127.0.0.1:5173，/api 代理到 host

# 可选：本地构建到 host/.../web/spa（供非 Docker 的 uvicorn 调试）
npm run build
```

- 改前端后发布：执行 `./rebuild.sh host`（镜像内 `npm ci && npm run build`），再浏览器强制刷新。
- 鉴权由前端 `AuthProvider` 处理：访问任意页面拉取 `/api/me`，401 自动跳 `/login`（GitHub OAuth）。

### 2) 使用重建脚本（推荐）

仓库根目录提供脚本：`rebuild.sh`。
其中 `agent` 镜像通过 `docker build` 构建，不走 `docker compose build`。

```bash
# Host 代码或前端改动：重建 host 镜像（含 SPA）并重启
./rebuild.sh host
```

```bash
# Agent 代码改动：重建 agent 镜像 + 重建单个用户隔离容器
./rebuild.sh agent <user_id>
```

```bash
# 重建 host+agent 镜像并拉起服务（不主动 down）
./rebuild.sh full
```

```bash
# 同时顺带强制重建某个用户隔离容器
./rebuild.sh full <user_id>
```

```bash
# 仅重建基础设施（postgres/tei/host）
./rebuild.sh infra
```

### 3) 可选验证

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | rg "apod-user|agentpod-host"
```

## 鉴权与路由边界

- Bearer 仅允许：`/api/v1/chat/completions`、`/api/v1/responses`、`/api/v1/models`、`/api/v1/health`
- Session 允许：`/api/workspace/*`、`/api/me*`、`/api/settings/*`
- `agent_api_key` 访问 `/api/workspace/*` 应返回 `403`
- Session 访问 `/api/v1/*` 应返回 `403`

## 目录结构

```
.
├── pyproject.toml             # uv workspace 根
├── docker-compose.yml         # 宿主编排
├── Caddyfile                  # 反代（SSE 无缓冲）
├── host/                      # Host 控制平面
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/agentpod_host/
├── agent/                     # Agent 执行平面
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/agentpod_agent/
└── shared-skills/             # 公共技能库
```

## 常见问题排查

- `503 + Retry-After`：用户容器正在冷启动，等待后重试。
- 登录后无法对话：检查是否已保存 LLM 配置。
- SSE 无流式输出：确认反向代理未缓冲（见 `Caddyfile`）。
- 调用 workspace 接口 403：确认你在用 Session，而不是 Bearer key。

## P0 验收标准（DoD）

- 新用户首次登录 10s 内进入工作台，首轮对话首包 30s 内返回（需宿主已配置 `LLM_API_KEY`）。
- `/api/v1/chat/completions`、`/api/v1/responses` 与 `/api/v1/models` 鉴权通过；冷启动返回 `503 + Retry-After`。
- `agent_api_key` 调用 `/api/workspace/*` 一律 403；Session 调用 `/api/v1/*` 一律 403。
- 用户 A 容器从网络层无法访问用户 B 容器。
- 容器以 `uid=10001`、`cap_drop=ALL`、`read_only=true` 启动。
- 日志不出现明文密钥；业务容器无 `docker.sock` 挂载。
- SSE 端到端：首包 < 1s（不含 LLM），chunk 间隔 < 200ms。
