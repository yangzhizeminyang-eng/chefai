/**
 * 文件职责：@aicook/shared 跨端共享层的 vitest 配置（node 环境单测入口）。
 * 从 web-stage1 的 vitest 配置口径对齐：node 环境、仅收集 tests 目录下的 spec 文件。
 * 纯函数共享层无组件挂载需求，node 环境即可覆盖全部用例（含 fake timers）。
 */
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    /** node 环境：纯函数与计时器单测均无需浏览器/DOM */
    environment: 'node',
    /** 仅收集 tests 目录下的 spec 文件（如 tests/unit.spec.ts） */
    include: ['tests/**/*.spec.ts'],
  },
})
