# AgentPod Desktop（macOS）

内嵌 React 前端 + Python 单体 sidecar。打开即用，无需 Docker。

## 架构

```
用户 → AgentPod.app
         ├─ Gateway :1420 → 内嵌 SPA (dist-desktop)
         └─ Sidecar  :8080 → Host + Agent 单体 (FastAPI)
                ├─ ~/.agentpod/settings.json
                ├─ ~/.agentpod/host.sqlite
                ├─ ~/.agentpod/workspaces/*/agent.sqlite
                ├─ ~/.agentpod/attachments/
                └─ ~/.agentpod/models/  (fastembed ONNX)
```

## 前置条件

- Node.js + npm
- Rust stable + Cargo
- Python 3.11+

## 构建

```bash
./rebuild.sh sidecar   # 开发用 sidecar/.venv
./rebuild.sh desktop   # 打包 sidecar-venv + shared-skills + .app
```

`desktop` 会把独立 Python 环境打进 `.app` 的 `Resources/sidecar-venv/`，无需本机安装依赖。

## 配置

在应用内 **设置 → 对话模型（LLM）** 编辑，或直接改 `~/.agentpod/settings.json`。

| 字段 | 说明 |
|------|------|
| `llm.api_key` | 对话模型 API Key |
| `llm.base_url` / `llm.model` | LLM 端点与模型 |
| `tools.tavily_api_key` | 可选，网页搜索 |
| `tools.jina_api_key` | 可选，网页提取 |
| `embedding.model` | 默认 `BAAI/bge-small-zh-v1.5`（首次启动自动下载到 `~/.agentpod/models`） |

首次启动会自动生成 `secrets.*`（加密密钥、session、internal token）。

## 从 Docker 迁移数据

```bash
# 若卷仍在 Docker 中且可 inspect
./rebuild.sh migrate-docker

# 或先导出再迁移
docker run --rm -v apod-data-2:/from:ro -v "$PWD/export":/to alpine sh -c 'cp -a /from/. /to/'
./rebuild.sh migrate-docker --source "$PWD/export"
```

## 开发

```bash
./rebuild.sh sidecar
cd sidecar && source .venv/bin/activate && AGENTPOD_MONOLITH=1 uvicorn agentpod.main:app --host 127.0.0.1 --port 8080
cd frontend && npm run dev   # 或 npm run build:desktop + desktop npm run dev
```

## 环境变量（可选）

| 变量 | 说明 |
|------|------|
| `AGENTPOD_API_URL` | Gateway 反代目标，默认 `http://127.0.0.1:8080` |
| `AGENTPOD_PYTHON` | 指定 sidecar Python 可执行文件 |

## 系统通知

通知中心新消息会额外镜像为 macOS 原生通知。请在 **系统设置 → 通知 → AgentPod** 允许通知。
