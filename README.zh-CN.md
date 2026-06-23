# Locus Agent

[![CI](https://github.com/sha2kyou/locusagent/actions/workflows/ci.yml/badge.svg)](https://github.com/sha2kyou/locusagent/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/sha2kyou/locusagent?label=release&sort=semver)](https://github.com/sha2kyou/locusagent/releases)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[English](./README.md) · [简体中文](./README.zh-CN.md)

**Locus Agent** 是一款本地优先的桌面 AI Agent，支持 macOS 与 Windows。它以**可交付成果**为核心——报告、脚本、工作区文件，以及可按类别归档、日后召回与迭代的 **Artifacts**。聊天是引导方式；重点是能长期保留的产出。

把需求变成成品：Agent 可读写工作区文件、运行代码、搜索网页、连接 MCP 服务、跨会话记忆上下文，并按计划执行定时任务。一切都在本机完成。

运行时数据位于 `~/.locusagent/`（macOS/Linux）或 `%USERPROFILE%\.locusagent\`（Windows），包括 `settings.json`、SQLite 数据库及各工作区存储。

![Locus Agent 主窗口 — 侧边栏导航、聊天历史与格式化的 Agent 报告](docs/images/main-window.png)

## 关于名称

**Locus**（拉丁语：*place*，*position*）指某物被定义的固定位置——磁盘上的工作区、记忆的作用域、Agent 运行的边界。

**Locus Agent** 是在**你的机器**上这一位置运行的 AI Agent，而不是需要反复补充上下文的远程网页：

- **本地锚点（Local locus）** — Host 与 Agent 以 sidecar 形式打包，监听 `127.0.0.1:21223`；对话、工具调用与 SQLite 数据均保存在 `~/.locusagent/` 下。
- **工作区锚点（Workspace loci）** — 每个工作区是独立空间：文件、会话、记忆、Skills 与 MCP 配置互不干扰。
- **Agent** — 执行层：文件 I/O、沙箱代码、终端、网页搜索、MCP、定时任务与可交付成果。

合起来即：*锚定在你可控的本地位置的 Agent。*

## 功能亮点

- **快捷对话窗** — 全局快捷键（默认 `Cmd+Shift+K` / `Ctrl+Shift+K`）可在桌面任意位置打开轻量聊天浮层，流式回复无需切回主窗口；快捷键、窗口位置与开关可在设置中配置。

![Locus Agent 快捷对话 — 浮层流式回复与 LaTeX 渲染](docs/images/quick-window.png)

- **本地与隐私** — 对话、记忆与工作区文件留在本机；除 LLM 提供商 API Key 外，无需云账号。
- **工具原生 Agent 循环** — 在同一聊天界面中完成文件 I/O、沙箱代码执行、受控终端命令、网页搜索/提取与文件交付。
- **Skills** — 可复用的指令包：内置（只读），以及各工作区可自建或从 GitHub/zip URL 安装的用户 Skills。
- **MCP** — 接入 Model Context Protocol 服务器，连接日历、数据库、API 等外部系统。
- **记忆** — 跨会话的长期事实/偏好与短期笔记，按工作区隔离。
- **Artifacts** — 将可交付成果按类别归档，日后召回。
- **定时任务** — 类 Cron 的提示词，在后台自动执行。
- **多工作区** — 不同项目或客户拥有独立的文件、会话、记忆与配置。
- **稳健的流式传输** — 导航离开或刷新后，Agent 仍在本地后台继续运行；UI 可重连进行中的任务。

## 安装

### macOS（Apple Silicon）

**仅 arm64** — 通过 Homebrew：

```bash
brew tap sha2kyou/tap
brew trust --cask sha2kyou/tap/locusagent
brew install --cask locusagent
```

当前发布版不支持 Intel Mac。

### Windows（x64）

从 [GitHub Releases](https://github.com/sha2kyou/locusagent/releases) 下载最新安装包：

`LocusAgent_<version>_windows-x64.exe`

运行安装程序后，从「开始」菜单或桌面快捷方式启动 **Locus Agent**。**仅 x64（64 位）** — 当前发布版不支持 ARM64 Windows。

### 首次启动

1. 打开 **设置 → 模型**，添加 LLM 提供商 API Key 与主模型。
2. 可选：在 **设置 → 工具** 中配置网页搜索/提取 Key 并启用工具。
3. 开始聊天。可附加文件、在 Agent 生成时排队后续消息，或从侧边栏切换工作区。

## 项目结构

```
locusagent/
├── frontend/          React + Vite SPA（聊天 UI、设置、路由）
├── desktop/           Tauri 2 壳（macOS .app / .dmg，Windows NSIS 安装包）
├── sidecar/           打包的 Python 入口（Host + Agent 单体）
├── host/              设置、API 代理、工作区元数据
├── agent/             聊天循环、工具、记忆、MCP、持久化
├── shared/            共享设置与工具函数
├── shared-skills/     应用内置 Skills
├── tests/             Python 集成测试
└── scripts/           版本同步、打包辅助脚本
```

Sidecar 监听 **`127.0.0.1:21223`**，同源提供 UI 与 API。生产环境中桌面应用内嵌独立 Python 3.11 运行时；开发时通常自行运行 `locusagent-serve`（见下文）。

## 从源码构建

通用依赖：[uv](https://docs.astral.sh/uv/)、Node.js 22+、Rust（stable）。生产包通过 uv 内嵌独立 Python 3.11 运行时。

### macOS（Apple Silicon）

**要求：** macOS（Apple Silicon）、Python 3.11+（本地开发；打包脚本使用 uv 管理的 Python）。

完整桌面构建（打包 venv + 前端 + Tauri release）：

```bash
./rebuild.sh
open dist/Locus\ Agent.app
```

产物复制到 `dist/`（`Locus Agent.app` 与 `LocusAgent_<version>_macos-arm64.dmg`）。

```bash
./rebuild.sh --fresh-venv              # 强制重建内嵌 Python（较慢）
python3 scripts/sync-version.py        # 同步 VERSION → 各 manifest
```

### Windows（x64）

**要求：** Windows 10/11 x64、PowerShell、[uv](https://docs.astral.sh/uv/)、Node.js 22+、带 `x86_64-pc-windows-msvc` target 的 Rust（`rustup target add x86_64-pc-windows-msvc`）。

完整桌面构建（打包 venv + 前端 + Tauri NSIS 安装包）：

```powershell
pwsh ./scripts/build-desktop-windows.ps1
```

安装包复制到 `dist/LocusAgent_<version>_windows-x64.exe`。

```powershell
pwsh ./scripts/build-desktop-windows.ps1 -FreshVenv   # 强制重建内嵌 Python（较慢）
uv run python scripts/sync-version.py                 # 同步 VERSION → 各 manifest
```

## 开发

### Sidecar（API + UI 宿主）

在仓库根目录：

```bash
uv sync --group dev
uv run locusagent-serve
```

进程绑定 `http://127.0.0.1:21223`，数据写入用户目录下的 `.locusagent`（见[配置](#配置)）。

### Python 测试

```bash
uv sync --group dev
uv run pytest tests/ -q
```

### 前端（Vite HMR）

在另一终端运行 sidecar 的前提下：

```bash
cd frontend
npm ci
npm run dev              # Vite 开发服务器；/api 代理至 :21223
npm run build:desktop    # Tauri / sidecar 静态 UI 的生产构建
npm run lint
npm run test:latex && npm run test:notifications && npm run test:toast && npm run test:stream-sync
```

### 桌面壳（Tauri）

先完成桌面 bundle 构建（在 `frontend/` 中 `npm run build:desktop`），启动 `locusagent-serve`，然后：

```bash
cd desktop
npm ci
npm run dev              # Tauri 窗口 → devUrl http://127.0.0.1:21223
```

## 配置

| 路径 | 用途 |
|------|------|
| `<home>/.locusagent/settings.json` | 全局设置（模型、工具 Key、Host 选项） |
| `<home>/.locusagent/host.sqlite` | Host 元数据（工作区注册表等） |
| `<home>/.locusagent/workspaces/<id>/agent.sqlite` | 该工作区的会话、消息、记忆、运行记录 |
| `<home>/.locusagent/workspaces/<id>/workspace/` | Agent 可读写的工作区文件 |
| `<home>/.locusagent/skills/` | 内置 Skills 镜像（启动时从应用刷新；只读） |
| `<home>/.locusagent/workspaces/<id>/skills/` | 工作区用户 Skills（UI 创建、`skill_install` 或 Agent `skill_manage`） |

`<home>` 在 macOS/Linux 为 `~`，在 Windows 为 `%USERPROFILE%`。可通过环境变量 `LOCUSAGENT_HOME` 覆盖。

参见 `shared/settings.example.json` 了解 Host 设置的注释示例。

## 文档

| 文档 | 读者 |
|------|------|
| [docs/LOCUSAGENT.md](./docs/LOCUSAGENT.md) | 应用内 AI Agent — 平台能力、工具与用户向约定 |
| [cliff.toml](./cliff.toml) + GitHub Releases | 打 tag 时自动生成的变更日志 |

## 许可证

采用 [Apache License, Version 2.0](LICENSE)。

Copyright © 2026 Locus Agent Team
