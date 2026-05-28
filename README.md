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

### 3) 启动整套服务

```bash
docker compose up -d --build
```

默认入口：`http://localhost`

## 启动后验证

### 健康检查

```bash
curl "http://localhost/health"
curl "http://localhost/api/v1/health"
```

### 首次使用路径

1. 浏览器打开 `http://localhost`
2. 用 GitHub 登录
3. 在设置页配置 LLM（BYOK）
4. 打开 `http://localhost/chat` 发起对话

### API 验证（Bearer）

拿到 `agent_api_key` 后可测试：

```bash
curl "http://localhost/api/v1/models" \
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

- 新用户首次登录 10s 内进入工作台，保存 BYOK 后 30s 内首轮对话首包返回。
- `/api/v1/chat/completions`、`/api/v1/responses` 与 `/api/v1/models` 鉴权通过；冷启动返回 `503 + Retry-After`。
- `agent_api_key` 调用 `/api/workspace/*` 一律 403；Session 调用 `/api/v1/*` 一律 403。
- 用户 A 容器从网络层无法访问用户 B 容器。
- 容器以 `uid=10001`、`cap_drop=ALL`、`read_only=true` 启动。
- 日志不出现明文密钥；业务容器无 `docker.sock` 挂载。
- SSE 端到端：首包 < 1s（不含 LLM），chunk 间隔 < 200ms。
