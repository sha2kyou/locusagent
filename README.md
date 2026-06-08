# AgentPod

macOS 桌面 AI Agent：打开即用，内置对话、Skills、MCP、Memory、定时任务与多工作区。

单体 sidecar（Host + Agent 同进程），无 Docker、无多用户账户；配置在 `settings.json`，数据在本地 SQLite。

## 架构

```
AgentPod.app
  ├─ Gateway :1420   内嵌 React UI（frontend/dist-desktop）
  └─ Sidecar :8080   Python 单体 FastAPI（host + agent + sidecar）
        └─ ~/.agentpod/
             ├── settings.json          LLM / 工具 Key / 时区 / secrets
             ├── host.sqlite            工作区、通知、定时任务、用量、MCP OAuth
             ├── workspaces/<id>/
             │    ├── agent.sqlite      会话、消息、记忆、产物…
             │    └── …                 MCP 配置等
             ├── attachments/           聊天附件
             ├── models/                fastembed ONNX 缓存
             └── skills/                用户技能
```

Embedding 使用内嵌 fastembed（默认 `BAAI/bge-small-zh-v1.5`），不依赖外部 TEI 服务。

## 快速开始

**依赖：** Python 3.11+、Node.js + npm、Rust + Cargo（打桌面包时需要）

```bash
# 1. 开发用 Python 环境（可选，调试后端）
./rebuild.sh sidecar

# 2. 构建桌面 App（默认命令）
./rebuild.sh
open dist/AgentPod.app
```

首次使用在 **设置 → 模型** 填写 LLM API Key，或编辑 `~/.agentpod/settings.json`（示例见 `shared/settings.example.json`）。

### 仅调试 Python（不打包）

```bash
./rebuild.sh sidecar
cd sidecar && source .venv/bin/activate
AGENTPOD_MONOLITH=1 uvicorn agentpod.main:app --host 127.0.0.1 --port 8080
```

前端开发：`cd frontend && npm run dev`（需 sidecar 已在 8080 运行或由 Tauri 拉起）。

## 重建命令

| 场景 | 命令 |
|------|------|
| 打安装包（改 frontend / host / agent 后） | `./rebuild.sh` |
| 只更新开发 venv | `./rebuild.sh sidecar` |
| bundle 内 Python 环境异常 | `./rebuild.sh desktop --fresh-venv` |
| 从旧 Docker 卷迁移数据 | `./rebuild.sh migrate-docker` |

## 应用路由

| 路径 | 功能 |
|------|------|
| `/chat` | 对话（SSE、附件、会话） |
| `/skills` | 技能库 |
| `/mcp` | MCP 服务与 OAuth |
| `/memory` | 长期记忆 |
| `/workspaces` | 工作区 |
| `/env-vars` | 环境变量 |
| `/scheduled-tasks` | 定时任务 |
| `/artifacts` | 制品库 |
| `/settings` | 通用 / 模型 / 用量 |

## 仓库结构

```
shared/          公共库（settings.json、embedding、存储）
host/            控制面 API（工作区、设置、代理、定时任务）
agent/           执行面（chat loop、tools、memory）
sidecar/         单体入口 agentpod.main
frontend/        React UI → dist-desktop
desktop/         Tauri macOS 壳
shared-skills/   内置技能模板
scripts/         版本同步、打包辅助、数据迁移
```

## Python 工程说明

各 Python 包在 `shared/`、`host/`、`agent/`、`sidecar/` 各有 `pyproject.toml` 声明依赖。

根目录 `pyproject.toml` 用于：

- **`scripts/sync-version.py`** 同步 `VERSION` 到各包版本号
- **pytest / ruff** 配置（`testpaths`、`pythonpath`、lint 规则）
- **可选 uv workspace**（存在 `uv.lock`；`uv sync` 可装 dev 依赖）

**打包与 `./rebuild.sh sidecar` 走 `pip install -e`，不依赖 uv。** 日常测试示例：

```bash
./rebuild.sh sidecar
cd sidecar && source .venv/bin/activate
pytest ../tests/host -q
```

## 鉴权

浏览器通过 **session cookie** 访问 `/api/*`；Agent 内部调用 Host 代理时使用 `X-Internal-Token`。无对外 Bearer API、无用户表。

## 常见问题

| 现象 | 处理 |
|------|------|
| 无法对话 | 设置页或 `settings.json` 配置 `llm.api_key` |
| 向量检索首次很慢 | 等待模型下载到 `~/.agentpod/models` |
| 桌面打不开后端 | 重新 `./rebuild.sh` |
| 旧 Docker 数据未出现 | `./rebuild.sh migrate-docker --force` |
| MCP OAuth 失败 | `app.mcp_oauth_redirect_uri` 应为 `http://127.0.0.1:1420/api/oauth/mcp/callback` |

更多桌面打包细节见 [`desktop/README.md`](desktop/README.md)。
