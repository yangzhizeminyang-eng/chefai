/**
 * 文件职责：后台管理端 Vite 构建配置。
 * - Vue 插件与 @ 别名（指向 src 目录）；
 * - 开发代理：将 /admin/v1 转发到本地 FastAPI 后端（http://localhost:8000），
 *   前端统一走相对路径请求，避免 CORS 问题；后端不可用时仅表现为接口异常（页面三态兜底）；
 * - vitest 配置：node 环境跑纯函数单测（不引入 jsdom）；
 * - 固定开发端口 5174 + strictPort=true：端口被占用时直接报错退出，杜绝端口漂移。
 */
/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端服务地址（本地 FastAPI 默认端口 8000）
const BACKEND_TARGET = 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  // 显式关闭 Vite 8 的实验性 DevTools，避免向应用页面注入额外调试模块。
  devtools: false,
  plugins: [
    vue(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 后台管理端固定端口 5174（与用户端 web-stage1 的 5173 区分）；
    // strictPort=true：端口被占用时 vite 启动失败退出，而不是静默漂移
    port: 5174,
    strictPort: true,
    // 开发代理：后台管理 API（/admin/v1）统一转发到后端
    proxy: {
      '/admin/v1': {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
    },
  },
  test: {
    // 纯函数单测跑 node 环境即可（不挂载组件，无需 jsdom）
    environment: 'node',
  },
})
