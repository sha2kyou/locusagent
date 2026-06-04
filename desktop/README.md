# AgentPod Desktop（macOS）

内嵌 React 前端 + 本地 gateway 反代 Host API。Postgres / Redis / Agent 容器等后端服务保持不变。

## 架构

```
AgentPod.app (Tauri WebView → http://127.0.0.1:1420)
  ├─ 静态 SPA（web/dist-desktop）
  └─ gateway 反代 /api/*、/health → Host API（默认 http://127.0.0.1:1223）
```

前端仍使用相对路径（`/api/me` 等），Cookie / OAuth / WebSocket 与浏览器访问同一 Host 时行为一致。

## 前置条件

- Node.js + npm（构建前端）
- Rust stable + Cargo（构建 Tauri）
- Host 及其他服务已启动（`./rebuild.sh host` 或 docker compose）

## 构建

```bash
# 推荐：仓库根目录一键构建
./build-desktop.sh
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

产物：`desktop/src-tauri/target/release/bundle/macos/AgentPod.app`

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

## 与浏览器版的差异

- 无 PWA / Service Worker（桌面构建未启用 `vite-plugin-pwa`）
- 需本地 gateway 与 Host 同时可达
- 默认 API 指向 Caddy 端口 `1223`，与 `docker-compose.yml` 一致
