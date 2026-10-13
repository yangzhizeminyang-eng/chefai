/**
 * 文件级注释：Vitest 配置——node 环境运行单元测试，别名与 vite.config.ts 保持一致。
 * 说明：测试目标为工具函数 / 状态逻辑（不依赖小程序运行时），页面与组件测试由后续任务补充。
 */
import { defineConfig } from 'vitest/config'
import path from 'node:path'

/**
 * 导出 Vitest 配置
 * @returns node 环境的 Vitest 配置对象（无异常路径，配置错误由 Vitest 启动时抛出）
 */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.spec.ts']
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@shared': path.resolve(__dirname, '../packages/shared/src')
    }
  }
})
