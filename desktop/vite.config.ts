import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    electron([
      {
        // Main process entry
        entry: 'src/main/index.ts',
        vite: {
          build: {
            outDir: 'dist-electron/main',
            rollupOptions: { external: ['electron'] },
          },
        },
      },
    ]),
    renderer(),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src/renderer') },
  },
  root: 'src/renderer',
  build: {
    outDir: path.resolve(__dirname, 'dist-renderer'),
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    // Dev: proxy API calls to ALIS backend
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
