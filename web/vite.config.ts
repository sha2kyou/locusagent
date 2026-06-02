import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const API_TARGET = process.env.API_TARGET ?? 'http://127.0.0.1:8080'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // 生产产物直接落到后端包内，由 FastAPI 托管
  build: {
    outDir: fileURLToPath(new URL('../host/src/agentpod_host/web/spa', import.meta.url)),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalized = id.replace(/\\/g, '/')

          if (normalized.includes('node_modules')) {
            if (
              normalized.includes('react-markdown') ||
              normalized.includes('/remark-') ||
              normalized.includes('/rehype-') ||
              normalized.includes('micromark') ||
              normalized.includes('/unified/')
            ) {
              return 'markdown-vendor'
            }
            return
          }

          // 懒加载路由 chunk 不得回引 entry（index.js），否则 Safari 动态 import 会失败。
          if (/\/features\/[^/]+\/[^/]+Route\.(tsx|ts)$/.test(normalized)) return
          if (/\/routes\/ChatRoute\.(tsx|ts)$/.test(normalized)) return

          if (
            normalized.includes('/web/src/app/') ||
            normalized.includes('/web/src/api/') ||
            normalized.includes('/web/src/components/') ||
            normalized.includes('/web/src/lib/')
          ) {
            return 'app-shared'
          }
        },
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: ({ name }) => {
          if (name?.endsWith('.css')) return 'assets/[name].css'
          return 'assets/[name][extname]'
        },
      },
    },
  },
  server: {
    proxy: {
      // 后端契约：/api/* 与 /health 由 FastAPI 提供
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
        // SSE：禁用代理缓冲，保证 chat/completions 流式逐包透传
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
