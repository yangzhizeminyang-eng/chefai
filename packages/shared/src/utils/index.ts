/**
 * 文件职责：@aicook/shared 纯函数工具层 barrel 统一出口。
 * 集中转发 src/utils 下 12 个纯函数模块的全部导出（unit / scaling / nutritionQuery /
 * seasonal / cover / recipe / today / searchRouting / askFlow / timer / inventory / apiError），
 * 消费方统一从本文件导入，便于后续新增模块时保持导入路径稳定
 * （web-mini 经 vite alias @shared 引用）。
 */
export * from './unit'
export * from './scaling'
export * from './nutritionQuery'
export * from './seasonal'
export * from './cover'
export * from './recipe'
export * from './today'
export * from './searchRouting'
export * from './askFlow'
export * from './timer'
export * from './inventory'
export * from './apiError'
