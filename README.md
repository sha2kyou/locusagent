# AgentPod

[![CI](https://github.com/sha2kyou/agentpod/actions/workflows/ci.yml/badge.svg)](https://github.com/sha2kyou/agentpod/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/sha2kyou/agentpod?label=release&sort=semver)](https://github.com/sha2kyou/agentpod/releases)
[![Downloads](https://img.shields.io/github/downloads/sha2kyou/agentpod/total)](https://github.com/sha2kyou/agentpod/releases)
[![macOS](https://img.shields.io/badge/platform-macOS%20(arm64)-000000?logo=apple&logoColor=white)](#install)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](#build-from-source)
[![Node.js](https://img.shields.io/badge/node.js-22+-339933?logo=nodedotjs&logoColor=white)](#development)
[![Rust](https://img.shields.io/badge/rust-stable-000000?logo=rust&logoColor=white)](#build-from-source)
[![Homebrew](https://img.shields.io/badge/Homebrew-agentpod-FCBB00?logo=homebrew&logoColor=white)](https://github.com/sha2kyou/homebrew-tap)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**AgentPod** is a local-first macOS desktop AI agent. Chat with an LLM that can read and write files in your workspace, run code, search the web, connect MCP servers, remember context across sessions, and automate recurring work — all with data stored on your machine.

Configuration and runtime data live under `~/.agentpod/` (`settings.json`, SQLite databases, and per-workspace storage).

## Highlights

- **Local & private** — Conversations, memory, and workspace files stay on your Mac. No cloud account required beyond your LLM provider API key.
- **Tool-native agent loop** — File I/O, sandboxed code execution, controlled terminal commands, web search/extract, and file delivery from a single chat UI.
- **Skills** — Reusable instruction packs (built-in, shared, and user-defined) loaded on demand for specialized workflows.
- **MCP** — Plug in Model Context Protocol servers for calendars, databases, APIs, and other external systems.
- **Memory** — Long-term facts/preferences and short-term notes that persist across sessions, scoped per workspace.
- **Artifacts** — Save deliverables into categorized libraries and recall them later.
- **Scheduled tasks** — Cron-style prompts that run automatically in the background.
- **Multi-workspace** — Separate files, sessions, memory, and settings for different projects or clients.
- **Resilient streaming** — Agent runs continue on the server side if you navigate away or refresh; the UI reconnects to in-progress runs.

## Install

macOS (Apple Silicon), via Homebrew:

```bash
brew tap sha2kyou/tap
brew trust --cask sha2kyou/tap/agentpod
brew install --cask agentpod
```

### First launch

1. Open **Settings → Models** and add your LLM provider API key and primary model.
2. Optionally configure web search/extract keys and enable tools under **Settings → Tools**.
3. Start chatting. Attach files, queue follow-up messages while the agent is generating, or switch workspaces from the sidebar.

## Project layout

```
agentpod/
├── frontend/          React + Vite SPA (chat UI, settings, routes)
├── desktop/           Tauri 2 shell (macOS .app / .dmg)
├── sidecar/           Bundled Python entrypoint (Host + Agent monolith)
├── host/              API gateway, auth, proxies, workspace orchestration
├── agent/             Chat loop, tools, memory, MCP, persistence
├── shared/            Shared settings & utilities
├── shared-skills/     Built-in Skills shipped with the app
├── tests/             Python integration tests
└── scripts/           Version sync, bundle helpers
```

At runtime the desktop app embeds a standalone Python 3.11 environment and serves the UI over a local HTTP port (`127.0.0.1:21223` in dev).

## Build from source

**Requirements:** macOS, Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 22+, Rust (stable).

Full desktop build (bundled venv + frontend + Tauri release):

```bash
./rebuild.sh
open dist/AgentPod.app
```

Artifacts are copied to `dist/` (`AgentPod.app` and `AgentPod_<version>_macos-arm64.dmg`).

Other commands:

```bash
./rebuild.sh sidecar          # editable dev venv only (sidecar/.venv)
./rebuild.sh desktop --fresh-venv   # force rebuild bundled Python (slow)
python3 scripts/sync-version.py     # sync VERSION → all manifests
```

## Development

### Python (sidecar / tests)

```bash
uv sync --group dev
uv run pytest tests/ -q
```

For an editable local sidecar venv: `./rebuild.sh sidecar`, then activate `sidecar/.venv`.

### Frontend

```bash
cd frontend
npm ci
npm run dev              # Vite dev server
npm run build:desktop    # production bundle for Tauri
npm run lint
npm run test:latex && npm run test:notifications && npm run test:toast
```

### Desktop (Tauri dev)

Run the sidecar/backend separately or use the bundled flow, then:

```bash
cd desktop
npm ci
npm run dev              # tauri dev → loads frontend from devUrl
```

## Configuration

| Location | Purpose |
|----------|---------|
| `~/.agentpod/settings.json` | Global settings (models, tool keys, host options) |
| `~/.agentpod/` SQLite | Sessions, messages, memory, artifacts metadata |
| Per-workspace dirs under `~/.agentpod/workspaces/` | Files, env vars, isolated state |

See `shared/settings.example.json` for a annotated example of host settings.

## Documentation

| Doc | Audience |
|-----|----------|
| [AGENT.md](./AGENT.md) | In-app AI agent — platform capabilities, tools, and user-facing conventions (Chinese) |
| [cliff.toml](./cliff.toml) + GitHub Releases | Changelog generated on tagged releases |

## License

Licensed under the [Apache License, Version 2.0](LICENSE).

Copyright © 2026 AgentPod Team

---

[![GitHub stars](https://img.shields.io/github/stars/sha2kyou/agentpod?style=social)](https://github.com/sha2kyou/agentpod/stargazers)
**Version:** [latest release](https://github.com/sha2kyou/agentpod/releases) · **Platform:** macOS (arm64)
