# AgentPod

macOS 桌面 AI Agent：对话、Skills、MCP、Memory、定时任务与多工作区，打开即用。

Host 与 Agent 以单体 sidecar 同进程运行；配置在 `settings.json`，数据保存在 `~/.agentpod/` 本地 SQLite。

## 安装

```bash
brew tap sha2kyou/tap
brew install --cask agentpod
```

首次启动在 **设置 → 模型** 填写 LLM API Key。

## 架构

```
AgentPod.app
  ├─ Gateway :1420   内嵌 React UI
  └─ Sidecar :8080   Python FastAPI（host + agent）
        └─ ~/.agentpod/
             ├── settings.json
             ├── host.sqlite
             ├── workspaces/<id>/agent.sqlite
             ├── attachments/
             ├── models/          fastembed ONNX
             └── skills/
```

## 构建

依赖 Python 3.11+、Node.js、Rust。

```bash
./rebuild.sh
open dist/AgentPod.app
```

| 命令 | 说明 |
|------|------|
| `./rebuild.sh` | 构建 `.app` / `.dmg` → `dist/` |
| `./rebuild.sh sidecar` | 更新开发 venv |
| `./rebuild.sh desktop --fresh-venv` | 完整重建 bundle 内 Python 环境 |

## 开发

**后端**

```bash
./rebuild.sh sidecar
cd sidecar && source .venv/bin/activate
AGENTPOD_MONOLITH=1 uvicorn agentpod.main:app --host 127.0.0.1 --port 8080
```

**前端**

```bash
cd frontend && npm install && npm run dev
```

**测试**

```bash
pytest ../tests -q
```

（在 `sidecar/.venv` 激活后执行。）

## 配置

`~/.agentpod/settings.json`，字段示例见 `shared/settings.example.json`：

| 字段 | 说明 |
|------|------|
| `llm.api_key` | 对话模型 Key |
| `llm.base_url` / `llm.model` | LLM 端点与模型 |
| `tools.tavily_api_key` | 网页搜索 |
| `tools.jina_api_key` | 网页抽取 |
| `app.timezone` | 时区 |

## 功能

| 路径 | 说明 |
|------|------|
| `/chat` | 对话、附件、会话 |
| `/skills` | 技能库 |
| `/mcp` | MCP 与 OAuth |
| `/memory` | 长期记忆 |
| `/workspaces` | 工作区 |
| `/scheduled-tasks` | 定时任务 |
| `/artifacts` | 制品库 |
| `/settings` | 模型与用量 |

## 仓库

```
shared/    host/    agent/    sidecar/    frontend/    desktop/    shared-skills/
```

前端开发说明见 [`frontend/README.md`](frontend/README.md)。
