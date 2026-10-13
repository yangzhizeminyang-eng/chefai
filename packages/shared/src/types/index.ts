/**
 * 文件职责：@aicook/shared 类型层 barrel 统一出口。
 * 集中转发 src/types/api.ts 的全部后端契约类型，消费方统一从本文件导入，
 * 便于后续新增类型模块时保持导入路径稳定（web-mini 经 vite alias @shared 引用）。
 */
export * from './api'
