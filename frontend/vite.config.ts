import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const API_TARGET = process.env.API_TARGET ?? 'http://127.0.0.1:21223'
/** 与 desktop/src-tauri/src/sidecar.rs DEV_FRONTEND_PORT 保持一致 */
const DEV_FRONTEND_PORT = 5173

/** 桌面壳开发：Vite HMR + 代理 sidecar API（`tauri dev` 自动启动） */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: DEV_FRONTEND_PORT,
    strictPort: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
            }
          })
        },
      },
      '/health': { target: API_TARGET, changeOrigin: true },
    },
  },
})
