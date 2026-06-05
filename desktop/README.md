# AgentPod Desktop（macOS）

内嵌 React 前端 + 本地 gateway 反代 Host API。Postgres / Redis / Agent 容器等后端服务保持不变。

## 架构

图例：`──→` 请求流向，`├─` 分流

```
【日常请求】
用户 → AgentPod.app → Gateway :1420
                         ├─ 页面 → dist-desktop（web/dist-desktop）
                         └─ API  → Caddy :1223 → Host :8080
                                    → Postgres / Redis / Agent 容器

【OAuth 登录】GitHub Callback 在 Host，不在 :1420
App 登录 → 系统浏览器 → Gateway :1420 → Host → GitHub
        → 回调 OAUTH_REDIRECT_URI → agentpod:// → 写入 Session

【通知】
Host WebSocket → Gateway → 应用 toast/铃铛 + macOS 系统通知
```

服务端全貌见根目录 [`README.md`](../README.md#架构概览)。

## 前置条件

- Node.js + npm（构建前端）
- Rust stable + Cargo（构建 Tauri）
- Host 及其他服务已启动（`./rebuild.sh host` 或 docker compose）

## 构建

```bash
# 推荐：仓库根目录
./rebuild.sh desktop
```

或分步：

```bash
# 1. 构建桌面版前端
cd web
npm install
npm run build:desktop

# 2. 构建 .app / .dmg
cd ../desktop
npm install
npm run build
```

产物：

- `desktop/src-tauri/target/release/bundle/macos/AgentPod.app`
- `desktop/src-tauri/target/release/bundle/dmg/AgentPod_<version>_aarch64.dmg`（版本见仓库根目录 `VERSION`）

改 `web/`（桌面构建）或 `desktop/` 后执行 `./rebuild.sh desktop`（`./build-desktop.sh` 为等价别名）；与 `./rebuild.sh host` 独立。

## 开发

```bash
cd desktop
npm install
npm run dev
```

`tauri dev` 会先执行 `web` 的 `build:desktop`，再启动 gateway 与 WebView。

## 环境变量

| 变量 | 说明 |
|------|------|
| `AGENTPOD_API_URL` | Host API 根地址，默认 `http://127.0.0.1:1223`（Caddy 入口） |

示例：

```bash
AGENTPOD_API_URL=http://127.0.0.1:1223 npm run dev
```

## Host 仅 API 模式

Docker 部署默认 `SERVE_SPA=0`：Host 不托管 SPA，在线页面由 **web** 容器提供。桌面应用仍通过内嵌 `dist-desktop` + 本地 gateway 访问同一套 API。

## OAuth（GitHub）

桌面端使用 **系统浏览器登录 + Deep Link 回应用**，Web 端仍走原有同页 OAuth，互不影响。

1. App 内点击登录 → 系统浏览器经 gateway 打开 `/api/oauth/github/login?client=desktop`
2. GitHub 回调 **`OAUTH_REDIRECT_URI`**（与 Web 共用，由 state 区分客户端）
3. Host 签发一次性 exchange token → 重定向 `agentpod://oauth/callback?exchange=...`
4. macOS 唤起 AgentPod → WebView 访问 `/api/oauth/desktop/exchange` 写入 Session

GitHub OAuth App 只能配置 **一个** Authorization callback URL，填与 Web 相同的 `OAUTH_REDIRECT_URI` 即可，例如：

```
http://localhost/api/oauth/github/callback
```

注意 `localhost` 与 `127.0.0.1` 在 GitHub 视为不同 URL，须与 `.env` 中 `OAUTH_REDIRECT_URI` 完全一致。

MCP OAuth 仍建议在浏览器版完成；桌面 MCP 授权可后续扩展。

**关于 `http://127.0.0.1:1420/api/oauth/github/login?client=desktop`**

这是 App 内点击登录时由系统浏览器打开的 **gateway 入口**，不是 GitHub OAuth App 里要填的 Callback URL。仅在 **AgentPod.app 已运行** 时可访问；GitHub 回调仍走 `.env` 中的 `OAUTH_REDIRECT_URI`（Host 地址，如 `http://127.0.0.1:1223/api/oauth/github/callback`）。

## 系统通知

桌面端在保留应用内 **toast** 与通知铃铛的前提下，将通知中心（WebSocket `/api/notifications/ws`）的新条目 **额外镜像** 为 macOS 原生通知（`tauri-plugin-notification` → `plugin:notification|notify`）。

- 内容：与通知中心一致，使用条目的 `title` / `body`
- 不替代 toast；Web 浏览器版无系统通知
- 首次使用请在 **系统设置 → 通知 → AgentPod** 允许通知
- 应用在前台时可能只进通知中心、不弹横幅（取决于 macOS 专注模式等系统设置）

## 与浏览器版的差异

- 需本地 gateway 与 Host 同时可达
- 默认 API 指向 Caddy 端口 `1223`，与 `docker-compose.yml` 一致
- 通知中心新消息会额外触发 macOS 系统通知
