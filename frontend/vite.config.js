import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The app runs entirely in the browser: no backend, so no dev proxy. (A proxy
// on /classes, /lessons, /grading, /parent-updates and /workflow would swallow
// those SPA routes and break deep links.)
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 1200 },
})