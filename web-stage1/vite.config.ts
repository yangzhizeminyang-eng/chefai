/**
 * 文件职责：Vite 构建配置。
 * - 保留脚手架的 Vue 插件与 @ 别名；
 * - 新增开发代理：将 /v1 与 /api 转发到本地 FastAPI 后端（http://localhost:8000），
 *   前端统一走相对路径请求，避免 CORS 问题；后端不可用时仅表现为接口异常（页面三态兜底）。
 * - 新增 vitest 测试配置（Task 11）：node 环境跑纯函数单测（不引入 jsdom，不影响既有 build/serve 与代理）。
 * - 固定开发端口（05-V1.1 §3.2）：server.port=5173 + strictPort=true，
 *   端口被占用时直接报错退出，杜绝 vite 冲突自增到 5174/5175 导致端口漂移。
 */
/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端服务地址（阶段一 FastAPI 默认端口 8000）
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
    // 固定开发端口 5173（05-V1.1 §3.2「显式指定，否则冲突自增端口不确定」）；
    // strictPort=true：端口被占用时 vite 启动失败退出，而不是静默漂移到 5174/5175
    port: 5173,
    strictPort: true,
    // 开发代理：/v1（业务 API）与 /api（健康检查等）统一转发到后端
    proxy: {
      '/v1': {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
      '/api': {
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
