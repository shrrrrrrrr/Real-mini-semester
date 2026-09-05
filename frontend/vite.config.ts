import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// 后端 FastAPI 地址：开发走本地代理，避免 CORS；生产可用相对路径或环境变量覆盖
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // 前端统一以 /api 开头访问后端，SSE 流式接口同样走代理
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
})
