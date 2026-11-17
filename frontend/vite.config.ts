import path from 'path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig(({ mode }) => ({
  plugins: [react()],

  // `npm run dev:mock` serves the in-browser API mock (src/mocks) instead of the backend
  define: mode === 'mock' ? { 'import.meta.env.VITE_USE_MOCK': JSON.stringify('true') } : {},

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
}))
