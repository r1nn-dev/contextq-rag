import path from 'path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      // must match tsconfig.json paths
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    proxy: {
      // forward /api/* to backend to avoid CORS in development
      // production: nginx handles the same /api -> :8080 routing
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})