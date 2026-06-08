import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// macOS 桌面壳：静态产物供 Tauri 本地 gateway 托管，API 由 gateway 反代到 Host。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist-desktop',
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
              normalized.includes('/katex/') ||
              normalized.includes('micromark') ||
              normalized.includes('/unified/')
            ) {
              return 'markdown-vendor'
            }
            return
          }

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
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: ({ name }) => {
          if (name?.endsWith('.css')) return 'assets/[name]-[hash].css'
          return 'assets/[name]-[hash][extname]'
        },
      },
    },
  },
})
