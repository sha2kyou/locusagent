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
