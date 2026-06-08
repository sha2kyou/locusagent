# AgentPod

macOS 桌面 AI Agent：对话、Skills、MCP、Memory、定时任务与多工作区。

配置与数据在 `~/.agentpod/`（`settings.json` + 本地 SQLite）。

## 安装

```bash
brew tap sha2kyou/tap
brew trust --cask sha2kyou/tap/agentpod
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
