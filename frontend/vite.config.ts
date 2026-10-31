import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.SUBSY_API ?? 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 1200 },
})
