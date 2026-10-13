/**
 * 文件职责：@aicook/shared 跨端共享层总出口（类型 + 纯函数工具 + 文案常量）。
 * 小程序端（web-mini）与 Web 端（web-stage1 同构复用）统一经本文件消费共享资产，
 * 配合 vite alias `@shared` → packages/shared/src 使用。
 */
export * from './types'
export * from './utils'
export * from './constants'
