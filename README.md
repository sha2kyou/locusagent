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

## 构建

依赖 Python 3.11+、Node.js、Rust。

```bash
./rebuild.sh
open dist/AgentPod.app
```

## 文档

- [AGENT.md](./AGENT.md) — 供应用内 Agent 阅读的平台能力说明（`agentpod` 工具加载此文件）
