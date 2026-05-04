import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    host: true,
    allowedHosts: ['.h89.cn', '192.168.31.165'],
    proxy: {
      '/api': {
        target: 'http://192.168.31.165:51180',
        changeOrigin: true,
      },
    },
  },
})
