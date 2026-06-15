# AgentPod

macOS desktop AI agent: chat, Skills, MCP, Memory, scheduled tasks, and multi-workspace support.

Configuration and data live in `~/.agentpod/` (`settings.json` + local SQLite).

## Install

```bash
brew tap sha2kyou/tap
brew trust --cask sha2kyou/tap/agentpod
brew install --cask agentpod
```

On first launch, add your LLM API key under **Settings → Models**.

## Build

Requires Python 3.11+, Node.js, and Rust.

```bash
./rebuild.sh
open dist/AgentPod.app
```

## Docs

- [AGENT.md](./AGENT.md) — Platform capability guide for the in-app agent (loaded by the `agentpod` tool)
